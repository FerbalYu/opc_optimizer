---
keywords: [go]
always: false
---
# Go Performance Optimization

## 内存分配
- 用 `sync.Pool` 复用频繁创建/销毁的对象，降低 GC 压力
- `make([]T, 0, cap)` 预分配 slice 容量，避免 append 时反复扩容
- 用 `strings.Builder` 替代 `fmt.Sprintf` / `+` 拼接字符串

## 并发
- goroutine 必须有退出路径（`context.WithCancel` / `select`），避免泄漏
- channel 缓冲区大小要合理：无缓冲用于同步，有缓冲用于削峰
- 高并发读多写少场景用 `sync.RWMutex` 替代 `sync.Mutex`
- 考虑 `atomic` 包替代简单计数器的 Mutex

## 接口与类型
- 避免不必要的 `interface{}` / `any` 类型断言（用泛型替代）
- 小结构体传值，大结构体传指针
- 接口定义在使用方，不要在实现方定义大接口

## I/O
- `bufio.Reader` / `bufio.Writer` 包装 I/O，减少系统调用
- HTTP Client 复用：全局 `http.Client`，不要每次请求新建
- JSON 序列化热路径考虑 `encoding/json` 的流式 API 或 jsoniter

## 编译 & 工具
- `go build -ldflags="-s -w"` 减小二进制体积
- `go vet` + `staticcheck` 捕获常见错误
- `pprof` 定位 CPU / 内存瓶颈再优化，避免过早优化
