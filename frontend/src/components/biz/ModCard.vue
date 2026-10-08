<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, ExternalLink, ImageOff, RefreshCw } from 'lucide-vue-next'
import { localPreview } from '@/api'
import type { ModView } from '@/api/types'
import { applyTone, desiredTone, formatBytes, inventoryTone } from '@/utils/format'
import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import StatusBadge from './StatusBadge.vue'

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
const workshopUrl = computed(
  () => `https://steamcommunity.com/sharedfiles/filedetails/?id=${props.mod.workshop_id}`,
)
</script>

<template>
  <article
    class="group relative flex flex-col overflow-hidden rounded-xl border bg-surface transition-[transform,border-color,box-shadow] duration-200"
    :class="selected
      ? 'border-accent ring-2 ring-accent/15'
      : 'border-line hover:-translate-y-0.5 hover:border-accent-line hover:shadow-lg hover:shadow-ink/[0.07]'"
  >
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
        class="size-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
        @error="failed = true"
      >
      <span v-else class="flex size-full flex-col items-center justify-center gap-1.5 text-ink-4">
        <ImageOff class="size-5" aria-hidden="true" />
        <span class="text-[11px]">无预览图</span>
      </span>
      <Badge v-if="mod.requires_restart" variant="warning" class="absolute left-2 top-2 shadow-sm">
        待重启
      </Badge>
    </button>

    <button
      type="button"
      class="absolute right-2 top-2 z-10 flex size-6 items-center justify-center rounded-md border transition-colors"
      :class="selected
        ? 'border-accent bg-accent text-white'
        : 'border-white/60 bg-ink/35 text-white/90 backdrop-blur-sm hover:bg-ink/55'"
      :aria-pressed="selected"
      :aria-label="selected ? '取消选择' : '选择该 Mod'"
      @click.stop="emit('toggle')"
    >
      <Check v-if="selected" class="size-3.5" aria-hidden="true" />
    </button>

    <div class="flex flex-1 flex-col gap-2 p-3">
      <div class="flex flex-wrap items-center gap-1.5">
        <StatusBadge
          :tone="inventoryTone(mod.inventory_state)"
          :label="mod.inventory_zh || mod.inventory_state"
        />
        <StatusBadge
          :tone="desiredTone(mod.desired_state)"
          :label="mod.desired_zh || mod.desired_state"
        />
        <StatusBadge
          v-if="mod.apply_state !== 'unmanaged'"
          :tone="applyTone(mod.apply_state)"
          :label="mod.apply_zh || mod.apply_state"
        />
        <span v-else class="text-[11.5px] text-ink-4">未接管</span>
      </div>

      <button
        type="button"
        class="truncate text-left text-[13.5px] font-semibold leading-5 text-ink transition-colors hover:text-accent"
        :title="title"
        @click="emit('open')"
      >
        {{ title }}
      </button>

      <div class="flex items-center gap-1.5 text-[11.5px] text-ink-4">
        <span class="mono">ID {{ mod.workshop_id }}</span>
        <span aria-hidden="true">·</span>
        <span class="mono num">{{ formatBytes(mod.size_bytes) }}</span>
        <span class="spacer" />
        <a
          :href="workshopUrl"
          target="_blank"
          rel="noopener"
          class="inline-flex items-center text-ink-4 transition-colors hover:text-accent"
          title="打开创意工坊页面"
          @click.stop
        >
          <ExternalLink class="size-3.5" aria-hidden="true" />
        </a>
      </div>

      <div class="mt-auto flex flex-wrap items-center gap-1 border-t border-line pt-2.5">
        <Button
          size="sm"
          variant="ghost"
          :disabled="readOnly || mod.desired_state === 'enabled'"
          @click.stop="emit('enable')"
        >
          启用
        </Button>
        <Button
          size="sm"
          variant="ghost"
          :disabled="readOnly || mod.desired_state === 'disabled'"
          @click.stop="emit('disable')"
        >
          禁用
        </Button>
        <Button
          size="sm"
          variant="ghost"
          class="text-danger hover:bg-danger-soft hover:text-danger"
          :disabled="readOnly || mod.protected"
          :title="mod.protected ? mod.protected_reason : '删除'"
          @click.stop="emit('remove')"
        >
          删除
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          class="ml-auto"
          :disabled="readOnly"
          title="刷新元数据"
          aria-label="刷新元数据"
          @click.stop="emit('refresh')"
        >
          <RefreshCw class="size-3.5" aria-hidden="true" />
        </Button>
      </div>
    </div>
  </article>
</template>