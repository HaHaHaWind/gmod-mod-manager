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
  <section
    class="overflow-hidden rounded-xl border border-card-border bg-surface shadow-card transition-[box-shadow] duration-[400ms] ease-in-out hover:shadow-card-hover"
  >
    <header
      v-if="title || $slots.actions"
      class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-line px-5 py-3.5"
    >
      <div class="min-w-0">
        <h2 v-if="title" class="truncate text-[14px] font-semibold tracking-tight text-ink">
          {{ title }}
        </h2>
        <p v-if="description" class="mt-0.5 text-[12.5px] leading-5 text-ink-3">{{ description }}</p>
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