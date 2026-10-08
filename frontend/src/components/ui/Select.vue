<script setup lang="ts">
import { computed } from 'vue'
import {
  SelectContent, SelectIcon, SelectItem, SelectItemIndicator, SelectItemText,
  SelectPortal, SelectRoot, SelectTrigger, SelectValue, SelectViewport,
} from 'reka-ui'
import { Check, ChevronDown } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    options: { value: string; label: string }[]
    placeholder?: string
    disabled?: boolean
    ariaLabel?: string
    class?: string
  }>(),
  { placeholder: '请选择' },
)

const model = defineModel<string>({ default: '' })

// reka-ui 禁止 SelectItem 使用空字符串值,内部用哨兵替换 ''。
const EMPTY = '__empty__'
const inner = computed({
  get: () => (model.value === '' ? EMPTY : model.value),
  set: (v: string) => { model.value = v === EMPTY ? '' : v },
})
const itemValue = (v: string) => (v === '' ? EMPTY : v)
</script>

<template>
  <SelectRoot v-model="inner" :disabled="disabled">
    <SelectTrigger
      :aria-label="ariaLabel"
      :class="cn(
        'inline-flex h-9 w-full items-center justify-between gap-2 rounded-xl border border-line',
        'bg-surface px-3 text-[13px] text-ink transition-colors hover:border-line-strong',
        'focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/35',
        'disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-3',
        props.class,
      )"
    >
      <SelectValue :placeholder="placeholder" class="truncate text-left" />
      <SelectIcon as-child>
        <ChevronDown class="size-3.5 shrink-0 text-ink-4" aria-hidden="true" />
      </SelectIcon>
    </SelectTrigger>
    <SelectPortal>
      <SelectContent
        position="popper"
        :side-offset="4"
        class="z-50 max-h-64 min-w-[var(--reka-select-trigger-width)] animate-ui-in overflow-hidden rounded-xl border border-line bg-surface shadow-pop"
      >
        <SelectViewport class="p-1">
          <SelectItem
            v-for="o in options"
            :key="o.value"
            :value="itemValue(o.value)"
            class="relative flex cursor-pointer select-none items-center rounded-lg py-1.5 pl-7 pr-2 text-[13px] text-ink-2 outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[highlighted]:bg-accent-soft data-[highlighted]:text-accent-strong"
          >
            <SelectItemIndicator class="absolute left-2 inline-flex items-center">
              <Check class="size-3.5 text-accent" aria-hidden="true" />
            </SelectItemIndicator>
            <SelectItemText>{{ o.label }}</SelectItemText>
          </SelectItem>
        </SelectViewport>
      </SelectContent>
    </SelectPortal>
  </SelectRoot>
</template>