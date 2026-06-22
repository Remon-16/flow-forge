# Trans 语法规范

## 规则

- Trans 字段格式：JSON 对象，key 为变量名，value 为 `StepID.response.field.path`
- 在 YAML 中可以使用原生映射格式，在 JSON 中使用对象格式
- 路径使用点号分隔嵌套字段
- 数组用 `[index]` 访问

## 适用范围

所有业务链路用例。
