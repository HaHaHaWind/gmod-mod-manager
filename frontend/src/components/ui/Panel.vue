<script setup lang="ts">
/** 面板容器:统一 12px 圆角、发丝边框与头部结构。 */
withDefaults(
  defineProps<{
    title?: string
    description?: string
    padded?: boolean
  }>(),
  { padded: true },
)
</script>

<template>
  <section class="overflow-hidden rounded-xl border border-line bg-surface">
    <header
      v-if="title || $slots.actions"
      class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line px-4 py-3"
    >
      <div class="min-w-0">
        <h2 v-if="title" class="truncate text-[13.5px] font-semibold tracking-tight text-ink">
          {{ title }}
        </h2>
        <p v-if="description" class="mt-0.5 text-[12px] leading-5 text-ink-3">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
        <slot name="actions" />
      </div>
    </header>
    <div :class="padded ? 'p-4' : ''">
      <slot />
    </div>
  </section>
</template>