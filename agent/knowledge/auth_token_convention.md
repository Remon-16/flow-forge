# Token 传递规范

## 规则

登录后，token 应放入请求头 Authorization 字段，格式为 `Bearer {token}`。

## 适用范围

所有需要认证的接口。
