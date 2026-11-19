/** Node 20 没有 EventSource,MSW 构造 SSE 处理器时需要它存在。测试里不使用事件流,放一个空实现即可。 */
if (typeof globalThis.EventSource === 'undefined') {
  class EventSourceStub {
    addEventListener() {}
    removeEventListener() {}
    close() {}
  }
  Object.assign(globalThis, { EventSource: EventSourceStub })
}
