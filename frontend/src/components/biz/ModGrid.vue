<script setup lang="ts">
import { Boxes } from 'lucide-vue-next'
import type { ModView } from '@/api/types'
import EmptyState from '@/components/ui/EmptyState.vue'
import Skeleton from '@/components/ui/Skeleton.vue'
import ModCard from './ModCard.vue'

defineProps<{
  mods: ModView[]
  loading: boolean
  readOnly: boolean
  selected: string[]
}>()

const emit = defineEmits<{
  open: [wid: string]
  toggle: [wid: string]
  enable: [wid: string]
  disable: [wid: string]
  remove: [wid: string]
  refresh: [wid: string]
}>()
</script>

<template>
  <div
    v-if="loading && mods.length === 0"
    class="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-5"
  >
    <div
      v-for="i in 8"
      :key="i"
      class="overflow-hidden rounded-2xl border border-line bg-surface shadow-card"
    >
      <Skeleton class="aspect-video rounded-none" />
      <div class="flex flex-col gap-2 p-4">
        <div class="flex gap-1.5">
          <Skeleton class="h-[18px] w-14" />
          <Skeleton class="h-[18px] w-12" />
        </div>
        <Skeleton class="h-4 w-3/4" />
        <Skeleton class="h-3 w-1/2" />
        <Skeleton class="mt-2 h-7 w-full" />
      </div>
    </div>
  </div>

  <EmptyState
    v-else-if="mods.length === 0"
    title="没有匹配的 Mod"
    description="调整搜索关键词或筛选条件后重试;也可以先执行一次扫描缓存。"
  >
    <template #icon><Boxes class="size-5" aria-hidden="true" /></template>
  </EmptyState>

  <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-5">
    <ModCard
      v-for="m in mods"
      :key="m.workshop_id"
      :mod="m"
      :selected="selected.includes(m.workshop_id)"
      :read-only="readOnly"
      @open="emit('open', m.workshop_id)"
      @toggle="emit('toggle', m.workshop_id)"
      @enable="emit('enable', m.workshop_id)"
      @disable="emit('disable', m.workshop_id)"
      @remove="emit('remove', m.workshop_id)"
      @refresh="emit('refresh', m.workshop_id)"
    />
  </div>
</template>