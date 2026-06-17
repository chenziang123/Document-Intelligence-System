<script setup>
defineProps({
  showText: { type: Boolean, default: true },
})
</script>

<template>
  <div class="brand-logo" :class="{ 'brand-logo--icon-only': !showText }">
    <div class="brand-logo__mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" class="brand-logo__svg">
        <path
          d="M5 4.5A1.5 1.5 0 0 1 6.5 3h7.7L19 7.8V19.5A1.5 1.5 0 0 1 17.5 21h-11A1.5 1.5 0 0 1 5 19.5z"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linejoin="round"
        />
        <path
          d="M13.5 3v4.2h4.2"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linejoin="round"
        />
        <path
          d="M8.5 12.5h7M8.5 16h4.5"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
        />
      </svg>
    </div>
    <div v-if="showText" class="brand-logo__copy">
      <span class="brand-logo__title">识墨文坊</span>
      <span class="brand-logo__sub">SHIMOWENFANG</span>
    </div>
  </div>
</template>

<style scoped>
.brand-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-logo__mark {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  background: var(--primary);
  color: var(--primary-foreground);
  box-shadow: var(--shadow-soft);
  flex-shrink: 0;
}

.brand-logo__svg {
  width: 20px;
  height: 20px;
}

.brand-logo__copy {
  display: flex;
  flex-direction: column;
  line-height: 1;
}

.brand-logo__title {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--foreground);
}

.brand-logo__sub {
  margin-top: 3px;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--muted-foreground);
}
</style>
