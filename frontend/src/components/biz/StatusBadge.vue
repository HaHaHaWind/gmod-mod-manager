<script setup lang="ts">
import Badge from '@/components/ui/Badge.vue'
import type { Tone } from '@/utils/format'

withDefaults(defineProps<{ tone?: Tone; label?: string }>(), { tone: 'neutral' })
</script>

<template>
  <Badge :variant="tone"><slot>{{ label }}</slot></Badge>
</template>