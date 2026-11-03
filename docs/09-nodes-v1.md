# Weft v1 节点规格

<!-- 由代码节点声明自动生成，请勿手工编辑。 -->

|类型|名称|分类|执行 lane|缓存策略|说明|
| --- | --- | --- | --- | --- | --- |
|`file.list`|List Files|file|trusted_worker|pure|列出目录中的文件与目录|
|`flow.if`|If|flow|trusted_service|pure|按受限 Python 表达式选择分支|
|`flow.merge`|Merge|flow|trusted_service|pure|汇合两个可部分到达的表格分支|
|`flow.switch`|Switch|flow|trusted_service|pure|按变量值选择命名分支|
|`flow.trigger`|Trigger|flow|trusted_service|side_effect|手动、聊天、定时、文件或 HTTP 工作流入口|
|`flow.variable`|Variable|flow|trusted_worker|pure|定义流变量|
|`flow.wait`|Wait|flow|trusted_service|side_effect|等待指定秒数并响应取消|
|`table.column_filter`|Column Filter|table|trusted_worker|pure|按名称或通配符筛选列|
|`table.column_rename`|Column Rename|table|trusted_worker|pure|重命名表格列|
|`table.read_csv`|Read CSV|table|trusted_worker|pure|读取 CSV 文件为表格|
|`table.read_json`|Read JSON|table|trusted_worker|pure|读取 JSON 数组或 JSON Lines 文件|
|`table.read_parquet`|Read Parquet|table|trusted_worker|pure|读取 Parquet 文件|
|`table.row_count`|Table Row Count|table|trusted_worker|pure|输出表格行数变量|
|`table.row_filter`|Row Filter|table|trusted_worker|pure|按单条件筛选行|
|`table.sorter`|Sorter|table|trusted_worker|pure|按多个列键稳定排序|
|`table.write_csv`|Write CSV|table|trusted_worker|side_effect|将表格写入 CSV 文件|
|`table.write_json`|Write JSON|table|trusted_worker|side_effect|将表格写入 JSON 数组或 JSON Lines|
|`table.write_parquet`|Write Parquet|table|trusted_worker|side_effect|将表格写入 Parquet 文件|

## List Files (`file.list`)

列出目录中的文件与目录

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "目录路径"
    },
    "pattern": {
      "type": "string",
      "description": "glob 过滤",
      "default": "*"
    },
    "recursive": {
      "type": "boolean",
      "description": "是否递归",
      "default": false
    }
  },
  "required": [
    "path"
  ]
}
```

## If (`flow.if`)

按受限 Python 表达式选择分支

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "condition": {
      "type": "string",
      "description": "变量作用域内的条件表达式"
    }
  },
  "required": [
    "condition"
  ]
}
```

## Merge (`flow.merge`)

汇合两个可部分到达的表格分支

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {}
}
```

## Switch (`flow.switch`)

按变量值选择命名分支

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "variable": {
      "type": "string",
      "description": "要匹配的变量名"
    },
    "cases": {
      "type": "object",
      "description": "值到输出端口名的映射"
    }
  },
  "required": [
    "variable",
    "cases"
  ]
}
```

## Trigger (`flow.trigger`)

手动、聊天、定时、文件或 HTTP 工作流入口

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "manual": {
      "type": "object",
      "description": "手动触发配置",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "是否启用手动触发"
        }
      }
    },
    "chat": {
      "type": "object",
      "description": "聊天触发配置",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "是否启用聊天触发"
        }
      }
    },
    "schedule": {
      "type": "object",
      "description": "定时触发配置",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "是否启用定时触发"
        },
        "schedules": {
          "type": "array",
          "description": "cron 或固定间隔列表"
        }
      }
    },
    "watch": {
      "type": "object",
      "description": "文件监听配置",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "是否启用文件监听"
        },
        "watches": {
          "type": "array",
          "description": "监听路径与规则"
        }
      }
    },
    "http": {
      "type": "object",
      "description": "HTTP 触发配置",
      "properties": {
        "enabled": {
          "type": "boolean",
          "description": "是否启用 HTTP 触发"
        },
        "token_hash": {
          "type": "string",
          "description": "工作流令牌哈希"
        }
      }
    }
  }
}
```

## Variable (`flow.variable`)

定义流变量

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "values": {
      "type": "array",
      "description": "变量定义列表"
    }
  },
  "required": [
    "values"
  ]
}
```

## Wait (`flow.wait`)

等待指定秒数并响应取消

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "duration_seconds": {
      "type": "number",
      "minimum": 0,
      "description": "等待秒数"
    }
  },
  "required": [
    "duration_seconds"
  ]
}
```

## Column Filter (`table.column_filter`)

按名称或通配符筛选列

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "description": "包含或排除",
      "enum": [
        "include",
        "exclude"
      ]
    },
    "columns": {
      "type": "array",
      "description": "列名或通配符列表"
    }
  },
  "required": [
    "mode",
    "columns"
  ]
}
```

## Column Rename (`table.column_rename`)

重命名表格列

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "mapping": {
      "type": "object",
      "description": "旧列名到新列名映射"
    }
  },
  "required": [
    "mapping"
  ]
}
```

## Read CSV (`table.read_csv`)

读取 CSV 文件为表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "CSV 文件路径"
    },
    "encoding": {
      "type": "string",
      "description": "编码",
      "default": "auto"
    },
    "separator": {
      "type": "string",
      "description": "分隔符",
      "default": "auto"
    },
    "header": {
      "type": "boolean",
      "description": "是否含表头",
      "default": true
    },
    "skip_rows": {
      "type": "integer",
      "description": "跳过行数",
      "default": 0
    }
  },
  "required": [
    "path"
  ]
}
```

## Read JSON (`table.read_json`)

读取 JSON 数组或 JSON Lines 文件

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "JSON 文件路径"
    }
  },
  "required": [
    "path"
  ]
}
```

## Read Parquet (`table.read_parquet`)

读取 Parquet 文件

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Parquet 文件路径"
    }
  },
  "required": [
    "path"
  ]
}
```

## Table Row Count (`table.row_count`)

输出表格行数变量

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {}
}
```

## Row Filter (`table.row_filter`)

按单条件筛选行

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "column": {
      "type": "string",
      "description": "列名"
    },
    "operator": {
      "type": "string",
      "description": "比较操作",
      "enum": [
        "==",
        "!=",
        ">",
        ">=",
        "<",
        "<=",
        "contains",
        "starts_with",
        "regex",
        "is_null",
        "is_not_null",
        "in"
      ]
    },
    "value": {
      "description": "比较值"
    }
  },
  "required": [
    "column",
    "operator"
  ]
}
```

## Sorter (`table.sorter`)

按多个列键稳定排序

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "keys": {
      "type": "array",
      "description": "排序列与方向列表"
    }
  },
  "required": [
    "keys"
  ]
}
```

## Write CSV (`table.write_csv`)

将表格写入 CSV 文件

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "输出文件路径"
    },
    "encoding": {
      "type": "string",
      "description": "编码",
      "default": "utf-8-sig"
    },
    "separator": {
      "type": "string",
      "description": "分隔符",
      "default": ","
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否覆盖已有文件",
      "default": true
    }
  },
  "required": [
    "path"
  ]
}
```

## Write JSON (`table.write_json`)

将表格写入 JSON 数组或 JSON Lines

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "输出文件路径"
    },
    "lines": {
      "type": "boolean",
      "description": "是否使用 JSON Lines",
      "default": false
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否覆盖已有文件",
      "default": true
    }
  },
  "required": [
    "path"
  ]
}
```

## Write Parquet (`table.write_parquet`)

将表格写入 Parquet 文件

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "输出文件路径"
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否覆盖已有文件",
      "default": true
    }
  },
  "required": [
    "path"
  ]
}
```
