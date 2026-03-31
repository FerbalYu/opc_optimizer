---
keywords: [javascript, typescript]
always: false
---
# JavaScript / TypeScript Performance Optimization

## Bundle & Loading
- 启用 tree-shaking：避免 `import * as`，使用命名导入
- 大模块用动态 `import()` 做代码分割（路由级 / 功能级）
- 图片/字体用 `loading="lazy"` 延迟加载

## Runtime Performance
- 使用 `const` 代替 `let`（如无重赋值），帮助引擎优化
- 避免在循环中创建闭包（闭包捕获变量开销大）
- `for...of` / `for` 循环性能优于 `forEach`（热路径中）
- 用 `Map` / `Set` 替代 plain object 做频繁查找

## Async & Event Loop
- 并行独立 Promise 时用 `Promise.all()` 而非依次 `await`
- 长任务用 `requestIdleCallback` 或 `setTimeout(fn, 0)` 分片
- 避免 `async` 函数中的同步阻塞（大数组排序、JSON.parse 等）

## DOM & Rendering
- 批量 DOM 操作用 `DocumentFragment` 或一次性 `innerHTML`
- 滚动/resize 事件用 `throttle` / `debounce`
- 用 CSS `transform` / `opacity` 做动画（触发 GPU 合成，避免 reflow）

## TypeScript Specific
- 优先使用 `interface` 而非 `type`（interface 合并更快）
- 避免过度使用 `any`，用 `unknown` + 类型守卫
- `enum` 可用 `as const` 对象替代，减少运行时代码
