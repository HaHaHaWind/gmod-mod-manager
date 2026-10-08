# GMod 服务端 Mod 加载机制调研报告

> 本文档是面板实现的事实依据。每条结论均标注来源等级:
> - **[官方]**:来自 Valve 官方 Wiki / 官方仓库原文
> - **[社区]**:来自社区普遍经验或第三方项目源码,官方未明确记载
> - **[未验证]**:无法核实,面板实现将采取保守策略并在 UI 如实标注
>
> 调研时间:2026-10-08。第三方项目 [gmpublisher](https://github.com/WilliamVenner/gmpublisher)(commit `0f0e4e49598547d262f35e37cade7932d226161e`)为 **GPL-3.0** 许可,本项目仅参考其交互设计,**未复制其任何源码**;Valve 的 gmad/gmadconvert 仓库**无 LICENSE 文件**,未参考其代码。

---

## 1. GMA 包格式 [官方]

依据:Valve 官方仓库 [gmad](https://github.com/Facepunch/gmad) 源码中的格式定义(`gmad.wxs` 注释与 `gmad.cpp`)。

```
偏移  类型      说明
0     char[4]   魔数 "GMAD"
4     uint8     版本号,当前 = 3;读取端必须拒绝 > 3
5     uint64    作者 SteamID(v2+ 实际写入 0,保护隐私)
13    uint64    时间戳(Unix 秒)
21    ...       仅版本 ≥ 2:必需内容列表(NUL 结尾字符串,空串结束)
21*   ...       标题(NUL 结尾字符串)
...   ...       描述(NUL 结尾字符串,可能较长)
...   ...       作者名(NUL 结尾字符串)
...   int32     Addon 版本(当前 = 1)
...   文件表:每条 = uint32 文件号(从 1 递增);
        文件号 ≠ 0:路径(NUL 结尾,小写)+ int64 大小 + uint32 CRC32
        文件号 = 0:文件表结束
...   文件数据:按文件表顺序连续存放,无显式偏移字段
尾部  uint32    整个文件(含头部与数据)的 CRC32 校验(v3)
```

关键实现结论:

1. **路径以小写存储**;扫描展示时应保留原样,GMA 内部路径不作大小写转换。
2. **数据无偏移表**:解析元数据只需顺序读文件表;解包必须顺序流式读取。
3. **int64 大小**:存在无符号溢出可能,解析器必须校验 `size ≥ 0` 且不超过文件实际剩余长度。
4. **尾部 CRC32 是整体校验**,验证一次需完整读盘(O(GB)),因此默认只做结构性校验,完整性校验由用户在详情页显式触发。
5. 恶意/损坏包防御:字符串长度上限、文件表条目数上限、路径越界拒绝(详见 `app/services/gma.py` 注释)。

## 2. 服务端加载 Workshop 内容的三条路径

### 2.1 Workshop 缓存目录 + srcds 启动参数 [官方 + 未验证]

- `+host_workshop_collection <合集ID>`:srcds 启动时通过 Steam Workshop 下载合集内容,缓存在 `steam_cache/content/4000/<ID>/garrysmod/addons/<name>.gma`。**[官方]**
- 缓存中已存在的包不会重新下载,但集合内容变化会引入新包。**[官方]**
- 缓存目录中的包是否自动挂载:`+host_workshop_collection` 指定合集时挂载合集成员;**未列入合集的孤立缓存包不会被挂载**——此条为社区普遍观察,**官方未逐字记载 [未验证]**。面板因此将"缓存存在但不在任何受管加载入口"的包标记为 `unmanaged_cache`,不断言其实际不加载。

### 2.2 原生 Workshop ID 清单 `cfg/srcds_workshop_ids.txt` [官方]

依据:GMod 官方 Wiki 页面 [Workshop_Addons_for_Dedicated_Servers](https://wiki.facepunch.com/gmod/Workshop_Addons_for_Dedicated_Servers)(2026-09 修订)。

- 格式为 **KeyValues**(与 `.vdf` 同族),需手动创建:

```
"my_workshop_addons"
{
    "1"
    {
        "wsid"    "123277559"
    }
    "2"
    {
        "wsid"    "369839281"
    }
}
```

- 序号键(`"1"`、`"2"`)仅为唯一键占位,无顺序语义(重复键在 KeyValues 中会覆盖,故必须递增)。
- 文档注明该能力**要求 2026 年 9 月 22 日及以后构建的服务端**(2026.09.22+)。注:官方更新公告发布于 2026-09-16,与 Wiki 标注日期存在 6 天差异,面板以 Wiki 原文为准,并在 UI 提示用户以服务器实际版本为准。
- 启用 = 该 ID 出现在文件中;禁用 = 从文件移除。**改文件后必须重启 srcds 才生效** [官方],运行中的实例不会感知变化。
- 与 `+host_workshop_collection` 的叠加/覆盖关系 **[未验证]**:面板冲突检测将"同 ID 同时出现在集合与清单"标为 `conflict`,交由管理员决策,不擅自处理。

### 2.3 本地受管加载(addons 目录)[官方 + 未验证]

- `addons/` 下的文件夹 addon(含 `addon.json` 的解包结构)会被服务端自动加载。**[官方]**
- `addons/` 下的 `.gma` 文件是否自动挂载:客户端**自建服务器(listen server)**会自动挂载;**专用服务器场景官方 Wiki 未明确记载 [未验证]**,社区经验为"部分版本会挂载"。因此面板的本地受管模式提供两种策略并要求现场冷启动验证:
  - `gma_copy`(默认):把缓存 GMA 复制为 `addons/gmm_<ID>_v<N>.gma`。最接近社区惯例,开销为磁盘副本。
  - `folder_extract`:解包为 `addons/gmm_<ID>/` 文件夹 addon。兼容性最好(官方确认文件夹 addon 会被加载),但大量小文件,I/O 与 inode 开销高。
- `game.MountGMA` 只能在运行时临时挂载,**不能热重载已加载的材质/模型**,且对专用服务器启动流程无持久作用。**[官方]** 面板因此不使用运行时挂载。
- `resource.AddWorkshop` 仅控制**客户端**下载,不是服务端安装手段。**[官方]**

## 3. 运行时状态为何默认 unknown [设计决定]

- 服务端没有"哪些 addon 已加载"的可靠运行时探针 API [官方确认无此 API]。
- 日志(旧)、进程存在、数据库状态都不能证明**当前**实例已加载某包。
- 因此 `runtime_state` 默认一律 `unknown`,UI 明确展示"未知(无运行时探针)"。

**探针补充(后续接入)**:srcds 在运行时会**自动写出** Workshop 挂载缓存——旧位置
`garrysmod/cfg/srcds_addons.txt`(注意:这是 srcds 生成的缓存,不是配置文件),新版已迁移到
`<srcds 根>/cache/srcds_addon_list_cache.txt`(见 Facepunch 提交记录 "Moved srcds workshop
cache file from cfg/srcds_addons.txt (too generic) to cache/srcds_addon_list_cache")。
它直接记录 srcds 挂载了哪些 Workshop ID,是 `runtime_state` 的直接证据源,面板已接入:
- 探针可读 → 清单内 ID 记 `loaded`,其余记 `not_loaded`;
- 探针缺失/不可读/禁用 → 一律保持 `unknown`,安全语义不变。
- 另注:原生 workshop 方式下 srcds 直接从 steam_cache 挂载 .gma,`garrysmod/addons/`
  目录为空是**正常现象**,不代表没有任何 addon 被加载。

## 4. Steam Web API [官方]

- `POST ISteamRemoteStorage/GetPublishedFileDetails/v1/`:表单 `itemcount` + `publishedfileids[0..n]`,返回 JSON `response.publishedfiledetails[]`。**无需 API Key。** 每项 `result=1` 表示成功。
- `POST ISteamRemoteStorage/GetCollectionDetails/v1/`:展开合集成员(`children[]`)。**无需 API Key。**
- 批量上限:官方文档未记载;社区普遍经验为单请求 ≤ 100。面板默认 `STEAM_BATCH_LIMIT=100` 并可配置。
- 字段映射:`title`、`description`(HTML)、`creator`、`preview_url`、`tags[]`、`file_size`、`time_created`、`time_updated`、`consumer_app_id`(须为 4000)。
- 封面等外部图片不直接转发给浏览器:面板经**安全预览代理**拉取(域名白名单、大小/类型限制),避免 SSRF 与混合内容。

## 5. 第三方工具现状

- [gmpublisher](https://github.com/WilliamVenner/gmpublisher):GPL-3.0,Tauri(Rust + Svelte)桌面工具,面向**作者发布**而非服务器管理;其"扫描/上传/发布"流程与本项目需求不同,仅借鉴其 GMA 元数据展示与批量操作交互。**未复制代码。**
- Valve [gmad](https://github.com/Facepunch/gmad):命令行打包/解包工具,无 LICENSE;面板不依赖、不调用、不复制,自实现纯 Python 解析器(依据第 1 节格式)。
- WorkshopDL 等下载器:与本项目无关,未参考。

## 6. 结论映射到实现

| 调研结论 | 实现位置 |
| --- | --- |
| GMA 结构解析 | `backend/app/services/gma.py` |
| srcds_workshop_ids.txt 读写 | `backend/app/services/idsfile.py` |
| 缓存扫描与五维状态调和 | `backend/app/services/scan.py` |
| 三种管理模式适配 | `backend/app/adapters/` |
| 禁用后外部重新引入的冲突 | `Exclusion` 表 + 冲突扫描 |
| 修改配置需重启 | `requires_restart` + 手动/systemd 两种 `SERVER_CONTROL_MODE` |
