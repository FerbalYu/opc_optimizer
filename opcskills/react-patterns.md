---
keywords: [react, jsx, tsx]
always: false
---
# React Optimization Patterns

## 避免不必要的重渲染
- 纯展示组件用 `React.memo()` 包裹
- 昂贵计算用 `useMemo(fn, deps)` 缓存结果
- 回调函数用 `useCallback(fn, deps)` 稳定引用
- 父组件传下来的对象/数组要 memoize，避免每次 render 新建引用

## 状态管理
- 状态尽量下沉 — 只在需要的最小组件层级持有
- 频繁更新的状态和静态内容分离到不同组件
- 用 `useReducer` 替代多个相关联的 `useState`
- Context 值要 memoize，避免 Provider 重渲染导致全树更新

## 列表渲染
- 超过 100 条的列表用 `react-window` 或 `react-virtuoso` 虚拟滚动
- `key` 必须稳定且唯一（不要用 index 做 key，除非列表不会变）
- 列表项组件用 `React.memo` 避免整体 re-render

## 数据获取
- 用 `React.lazy()` + `Suspense` 做路由级代码分割
- 数据获取用 SWR / React Query 管理缓存 + 去重
- 避免在 `useEffect` 中做未清理的订阅（return cleanup function）

## 表单
- 非受控表单用 `useRef` 代替 `useState` 减少 re-render
- 大型表单考虑 react-hook-form（最小化 re-render）
