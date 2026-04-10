---
title: Polyglot Signal Processor
---

## Fast Fourier Transform (C)

```c
int multiply(int a, int b) {
    return a * b;
}
```

## Data Pipeline (Python)

```python
def process_batch(data):
    return [x * 2 for x in data]
```

## Integration

```python
def combined(input_data):
    processed = process_batch(input_data)
    return sum(processed)
```
