# Demo Training Project

## train

`train` 用于启动训练。参数 `epochs` 默认值为 `100`。

```python
source_path = "data.csv"

# 正确：位置实参的局部变量名无需与形参名相同。
train(source_path, epochs=50, batch_size=32)

# 错误：path 是源码签名中不存在的关键字参数。
train(path="data.csv", epochs=50, batch_size=32)

# 错误：缺少必需的 data_path 参数。
train()
```

Parameters:
- path: training dataset
- dataset_file: legacy dataset file setting
- source_reference: location of the source records

命令行示例：

```bash
python app.py --model weights.pt --batch-size 32
```

配置示例：

```yaml
training:
  batch: 32
```
