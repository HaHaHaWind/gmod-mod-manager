<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Check, CloudDownload, ExternalLink, ImageOff, Info, MoreHorizontal,
  RefreshCw, Trash2,
} from 'lucide-vue-next'
import {
  DropdownMenuContent, DropdownMenuItem, DropdownMenuPortal,
  DropdownMenuRoot, DropdownMenuSeparator, DropdownMenuTrigger,
} from 'reka-ui'
import { localPreview } from '@/api'
import type { ModView } from '@/api/types'
import { formatBytes, primaryModStatus } from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{ mod: ModView; selected: boolean; readOnly: boolean }>()

const emit = defineEmits<{
  open: []
  toggle: []
  enable: []
  disable: []
  remove: []
  refresh: []
}>()

const failed = ref(false)
const hasPreview = computed(() => !!props.mod.preview_url && !failed.value)
const title = computed(() => props.mod.title || props.mod.folder_name || props.mod.workshop_id)
const status = computed(() => primaryModStatus(props.mod))
const workshopUrl = computed(
  () => `https://steamcommunity.com/sharedfiles/filedetails/?id=${props.mod.workshop_id}`,
)
</script>

<template>
  <article
    class="group relative flex flex-col overflow-hidden rounded-2xl border bg-surface shadow-card transition-[transform,border-color,box-shadow] duration-200"
    :class="selected
      ? 'border-accent ring-2 ring-accent/20'
      : 'border-line hover:-translate-y-1 hover:border-accent-line hover:shadow-pop'"
  >
    <!-- 封面:16:9,加载失败时回退占位 -->
    <button
      type="button"
      class="relative block aspect-video w-full overflow-hidden bg-surface-muted"
      :aria-label="`查看 ${title}`"
      @click="emit('open')"
    >
      <img
        v-if="hasPreview"
        :src="localPreview(mod.workshop_id)"
        :alt="title"
        loading="lazy"
        decoding="async"
        class="size-full object-cover transition-transform duration-200 group-hover:scale-[1.04]"
        @error="failed = true"
      >
      <span v-else class="flex size-full flex-col items-center justify-center gap-1.5 text-ink-4">
        <ImageOff class="size-5" aria-hidden="true" />
        <span class="text-[12px]">无预览图</span>
      </span>
      <span
        v-if="mod.category_zh"
        class="absolute bottom-2 left-2 rounded-md bg-ink/55 px-1.5 py-0.5 text-[12px] font-medium text-white backdrop-blur-sm"
      >
        {{ mod.category_zh }}
      </span>
    </button>

    <!-- 多选入口 -->
    <button
      type="button"
      class="absolute right-2 top-2 z-10 flex size-6 items-center justify-center rounded-md border transition-colors"
      :class="selected
        ? 'border-accent bg-accent text-white'
        : 'border-white/60 bg-ink/35 text-white/90 backdrop-blur-sm hover:bg-ink/55'"
      :aria-pressed="selected"
      :aria-label="selected ? '取消选择' : '选择该模组'"
      @click.stop="emit('toggle')"
    >
      <Check v-if="selected" class="size-3.5" aria-hidden="true" />
    </button>

    <div class="flex flex-1 flex-col gap-2 p-4">
      <!-- 单一主状态 + 保守提示 -->
      <div class="flex min-h-[22px] flex-wrap items-center gap-1.5">
        <Badge :variant="status.tone">{{ status.label }}</Badge>
        <Tooltip v-if="status.hint" :content="status.hint">
          <span class="inline-flex text-ink-4" aria-label="状态说明">
            <Info class="size-3.5" aria-hidden="true" />
          </span>
        </Tooltip>
      </div>

      <!-- 标题:最多两行 -->
      <button
        type="button"
        class="line-clamp-2 min-h-[40px] text-left text-[15px] font-semibold leading-5 tracking-tight text-ink transition-colors hover:text-accent"
        :title="title"
        @click="emit('open')"
      >
        {{ title }}
      </button>

      <!-- 次级信息:作者 / 分类 / 大小(ID 与路径收进详情) -->
      <div class="flex items-center gap-1.5 text-[12px] text-ink-3">
        <span v-if="mod.author_name" class="max-w-[45%] truncate">{{ mod.author_name }}</span>
        <span v-if="mod.author_name && mod.category_zh" aria-hidden="true">·</span>
        <span v-if="mod.category_zh" class="truncate">{{ mod.category_zh }}</span>
        <span class="spacer" />
        <span class="mono num shrink-0">{{ formatBytes(mod.size_bytes) }}</span>
      </div>

      <!-- 常驻动作:启用/禁用(进入变更预览) + 更多菜单 -->
      <div class="mt-auto flex items-center gap-1 border-t border-line pt-3">
        <Button
          size="sm"
          variant="secondary"
          class="flex-1"
          :disabled="readOnly || mod.desired_state === 'enabled'"
          title="创建启用变更,提交前可预览"
          @click.stop="emit('enable')"
        >
          启用
        </Button>
        <Button
          size="sm"
          variant="secondary"
          class="flex-1"
          :disabled="readOnly || mod.desired_state === 'disabled'"
          title="创建禁用变更,提交前可预览"
          @click.stop="emit('disable')"
        >
          禁用
        </Button>
        <DropdownMenuRoot>
          <DropdownMenuTrigger as-child>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="更多操作"
              @click.stop
            >
              <MoreHorizontal class="size-4" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent
              align="end"
              :side-offset="6"
              class="z-50 min-w-44 animate-ui-in rounded-xl border border-line bg-surface p-1 shadow-pop"
            >
              <DropdownMenuItem
                class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-surface-muted data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
                :disabled="readOnly"
                @select="emit('refresh')"
              >
                <RefreshCw class="size-3.5 text-ink-4" aria-hidden="true" />
                更新模组信息
              </DropdownMenuItem>
              <DropdownMenuItem
                class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-2 outline-none data-[highlighted]:bg-surface-muted"
                @select="() => {}"
              >
                <a
                  :href="workshopUrl"
                  target="_blank"
                  rel="noopener"
                  class="flex flex-1 items-center gap-2"
                  @click.stop
                >
                  <CloudDownload class="size-3.5 text-ink-4" aria-hidden="true" />
                  在创意工坊打开
                </a>
                <ExternalLink class="size-3 text-ink-4" aria-hidden="true" />
              </DropdownMenuItem>
              <DropdownMenuSeparator class="my-1 h-px bg-line" />
              <DropdownMenuItem
                class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-danger outline-none data-[highlighted]:bg-danger-soft data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
                :disabled="readOnly || mod.protected"
                @select="emit('remove')"
              >
                <Trash2 class="size-3.5" aria-hidden="true" />
                {{ mod.protected ? '受保护,不可移除' : '移至回收站' }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenuRoot>
      </div>
    </div>
  </article>
</template>
