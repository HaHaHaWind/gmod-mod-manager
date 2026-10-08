<script setup lang="ts">
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import Button from './Button.vue'
import Select from './Select.vue'
import { cn } from '@/lib/utils'

const props = withDefaults(
  defineProps<{
    page: number
    pageSize: number
    total: number
    pageSizes?: number[]
  }>(),
  { pageSizes: () => [20, 50, 100] },
)

const emit = defineEmits<{ 'update:page': [number]; 'update:pageSize': [number] }>()

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))

const pages = computed<(number | 'gap')[]>(() => {
  const t = totalPages.value
  const c = props.page
  if (t <= 7) return Array.from({ length: t }, (_, i) => i + 1)
  const out: (number | 'gap')[] = [1]
  const start = Math.max(2, c - 1)
  const end = Math.min(t - 1, c + 1)
  if (start > 2) out.push('gap')
  for (let i = start; i <= end; i++) out.push(i)
  if (end < t - 1) out.push('gap')
  out.push(t)
  return out
})

const sizeOptions = computed(() =>
  props.pageSizes.map((n) => ({ value: String(n), label: `${n} 条/页` })),
)
const sizeModel = computed({
  get: () => String(props.pageSize),
  set: (v: string) => emit('update:pageSize', Number(v)),
})

function go(p: number) {
  if (p >= 1 && p <= totalPages.value && p !== props.page) emit('update:page', p)
}
</script>

<template>
  <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
    <span class="small muted num">共 {{ total }} 条</span>
    <span class="spacer" />
    <Select v-model="sizeModel" :options="sizeOptions" class="w-[104px]" aria-label="每页条数" />
    <div class="flex items-center gap-1">
      <Button
        size="icon-sm"
        variant="secondary"
        :disabled="page <= 1"
        aria-label="上一页"
        @click="go(page - 1)"
      >
        <ChevronLeft class="size-3.5" aria-hidden="true" />
      </Button>
      <template v-for="(p, i) in pages" :key="`${p}-${i}`">
        <span v-if="p === 'gap'" class="px-1 text-ink-4">…</span>
        <Button
          v-else
          size="icon-sm"
          :variant="p === page ? 'primary' : 'secondary'"
          :aria-current="p === page ? 'page' : undefined"
          :class="cn('num', p === page ? '' : 'font-normal')"
          @click="go(p)"
        >
          {{ p }}
        </Button>
      </template>
      <Button
        size="icon-sm"
        variant="secondary"
        :disabled="page >= totalPages"
        aria-label="下一页"
        @click="go(page + 1)"
      >
        <ChevronRight class="size-3.5" aria-hidden="true" />
      </Button>
    </div>
  </div>
</template>