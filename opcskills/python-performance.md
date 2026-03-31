---
keywords: [python]
always: false
---
# Python Performance Optimization

## Memory & Object Model
- 使用 `__slots__` 减少实例内存开销（适用于大量实例的数据类）
- 用 `namedtuple` 或 `dataclass(slots=True)` 替代普通 dict 存储结构化数据
- 避免在循环中创建不必要的临时对象

## 循环与推导式
- 用 list/dict/set comprehension 替代手动 `for` + `append`
- 用 `itertools` (chain, islice, groupby) 替代手写循环逻辑
- 热循环中将全局函数/属性缓存到局部变量（避免重复 LOAD_GLOBAL）

## 并发与 I/O
- I/O 密集场景优先用 `asyncio`，其次 `concurrent.futures.ThreadPoolExecutor`
- CPU 密集场景用 `multiprocessing` 或 `ProcessPoolExecutor`
- 文件批量读取时用 `mmap` 或 `pathlib.read_bytes()` 减少系统调用

## 数据结构选择
- 频繁 `in` 判断用 `set` / `frozenset`，不要用 `list`
- 计数用 `collections.Counter`，不要手写 dict 累加
- FIFO 队列用 `collections.deque`，不要用 `list.pop(0)`

## Import & 启动
- 延迟导入重模块（`import inside function`），加速启动
- 避免模块顶层执行耗时操作（数据库连接、网络请求）
