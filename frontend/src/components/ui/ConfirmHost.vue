<script setup lang="ts">
import { useConfirm } from '@/composables/useConfirm'
import Dialog from './Dialog.vue'
import Button from './Button.vue'

const { state, settleConfirm } = useConfirm()
</script>

<template>
  <Dialog
    :open="!!state?.open"
    :title="state?.title ?? ''"
    width-class="max-w-md"
    @update:open="(v: boolean) => { if (!v) settleConfirm(false) }"
  >
    <p class="text-[13px] leading-6 text-ink-2">{{ state?.description }}</p>
    <p v-if="state?.danger" class="mt-2 text-[12.5px] text-danger">
      该操作不可恢复,请确认后继续。
    </p>
    <template #footer>
      <Button variant="secondary" @click="settleConfirm(false)">
        {{ state?.cancelText || '取消' }}
      </Button>
      <Button
        :variant="state?.danger ? 'danger' : 'primary'"
        @click="settleConfirm(true)"
      >
        {{ state?.confirmText || '确认' }}
      </Button>
    </template>
  </Dialog>
</template>