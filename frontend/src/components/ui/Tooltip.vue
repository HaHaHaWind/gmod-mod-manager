<script setup lang="ts">
import { TooltipContent, TooltipPortal, TooltipProvider, TooltipRoot, TooltipTrigger } from 'reka-ui'

withDefaults(
  defineProps<{ content: string; side?: 'top' | 'right' | 'bottom' | 'left' }>(),
  { side: 'bottom' },
)
</script>

<template>
  <TooltipProvider :delay-duration="180">
    <TooltipRoot>
      <TooltipTrigger as-child>
        <slot />
      </TooltipTrigger>
      <TooltipPortal>
        <TooltipContent
          :side="side"
          :side-offset="6"
          class="z-[60] max-w-xs animate-ui-in rounded-lg bg-[#1b232e] px-2.5 py-1.5 text-[11.5px] leading-4 text-white shadow-pop"
        >
          {{ content }}
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  </TooltipProvider>
</template>