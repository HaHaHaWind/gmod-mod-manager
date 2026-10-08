<script setup lang="ts">
// 根组件:路由出口 + 全局通知与确认宿主。
import ConfirmHost from '@/components/ui/ConfirmHost.vue'
import Toaster from '@/components/ui/Toaster.vue'
</script>

<template>
  <RouterView />
  <Toaster />
  <ConfirmHost />
</template>