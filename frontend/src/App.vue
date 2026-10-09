<script setup lang="ts">
// 根组件:路由出口(登录页↔主布局整体淡切) + 全局路由进度条 + 通知与确认宿主。
import ConfirmHost from '@/components/ui/ConfirmHost.vue'
import Toaster from '@/components/ui/Toaster.vue'
import RouteProgress from '@/components/ui/RouteProgress.vue'
</script>

<template>
  <RouterView v-slot="{ Component, route }">
    <Transition name="fade" mode="out-in">
      <component :is="Component" :key="route.name === 'login' ? 'login' : 'app'" />
    </Transition>
  </RouterView>
  <Toaster />
  <ConfirmHost />
  <RouteProgress />
</template>
