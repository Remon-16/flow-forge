# Inherit 字段格式说明

## 规则

登录步骤的 token 被后续步骤引用时，Inherit 格式为 JSON 对象：

```json
{
    "token": "Step01.data.token"
}
```

## 适用范围

所有包含登录的链路。
