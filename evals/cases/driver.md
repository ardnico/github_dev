# ケース D1

仕様: 終了処理では、非同期処理が停止してからMMIOを解放する。
以下は説明用の擬似Cであり、実際のカーネルAPIを再現したものではない。

```c
irq_handler(dev) { queue_work(dev->work); }
work(dev) { read_register(dev->mmio); }
remove(dev) {
    cancel_work_sync(dev->work);
    release_mapping(dev->mmio);
    stop_device_interrupts(dev);
    unregister_and_drain_irq(dev);
}
```

ドライバ解析と仕様照合の手順で終了処理をレビューしてください。ソース変更は不要です。
