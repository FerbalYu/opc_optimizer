---
keywords: [vue]
always: false
---
# Vue Optimization Patterns

## 响应式优化
- `computed` 代替 `watch` 做派生状态（computed 有缓存，watch 每次执行）
- 大数据集用 `shallowRef` / `shallowReactive` 避免深层递归响应化
- 只读数据用 `Object.freeze()` 或 `markRaw()` 跳过响应式代理

## 条件渲染
- 频繁切换用 `v-show`（只切 display），初始不渲染用 `v-if`（惰性）
- `v-if` 和 `v-for` 不要同时写在同一元素上（v-if 在外层包裹）

## 列表渲染
- 大列表 (>200 项) 使用虚拟滚动（vue-virtual-scroller / @tanstack/vue-virtual）
- `v-for` 必须提供稳定的 `:key`
- 列表项组件化 + 避免在 `v-for` 内写复杂逻辑

## 组件优化
- 组件懒加载：`defineAsyncComponent(() => import('./Heavy.vue'))`
- 大组件拆成细粒度子组件，缩小更新范围
- 全局组件注册改为按需导入

## 构建优化
- Vite：自动 tree-shaking，确认 `sideEffects: false`
- 路由懒加载：每个路由 `component: () => import(...)`
- 第三方库按需导入（如 lodash-es, element-plus auto-import）
