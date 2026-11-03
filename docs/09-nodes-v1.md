# Weft v1 节点规格

<!-- 由代码节点声明自动生成，请勿手工编辑。 -->

|类型|名称|分类|执行 lane|缓存策略|说明|
| --- | --- | --- | --- | --- | --- |
|`agent.llm_call`|LLM Call|agent|trusted_service|volatile|通过主机 LLMProxy 执行流式文本或 JSON 补全|
|`agent.loop`|Agent Loop|agent|trusted_service|volatile|执行可停止、可审计的 ReAct 工具调用循环|
|`agent.node_tool`|Node as Tool|agent|trusted_service|side_effect|把显式授权的节点包装为受控 Agent 工具|
|`agent.prompt_template`|Prompt Template|agent|trusted_service|volatile|用受限 Jinja2 模板组合变量与只读表格|
|`code.python`|Python Script|code|trusted_worker|side_effect|在可信 Worker 中执行用户 Python 代码|
|`excel.cell_update`|Excel Cell Update|excel|trusted_service|side_effect|原子更新若干不连续单元格，默认禁止公式|
|`excel.connect`|Excel Connect|excel|trusted_service|side_effect|连接可见 Excel 或创建独立的可见/隐藏实例|
|`excel.read_range`|Excel Read Range|excel|trusted_service|volatile|实时读取 Excel 区域、表对象或命名区域为表格|
|`excel.save`|Excel Save|excel|trusted_service|side_effect|显式保存或另存工作簿，不隐式覆盖文件|
|`excel.sheet`|Excel Sheet|excel|trusted_service|side_effect|创建、删除、重命名或清空工作表|
|`excel.sheet_names`|Excel Sheet Names|excel|trusted_service|volatile|列出工作表名、索引与可见状态|
|`excel.workbook`|Excel Workbook|excel|trusted_service|side_effect|引用已打开工作簿、打开文件或新建工作簿|
|`excel.write_table`|Excel Write Table|excel|trusted_service|side_effect|整块写入、追加或覆盖 Excel 工作表区域|
|`file.copy`|File Copy|file|trusted_worker|side_effect|复制文件或目录|
|`file.delete`|File Delete|file|trusted_worker|side_effect|移入回收站或永久删除|
|`file.list`|List Files|file|trusted_worker|pure|列出目录中的文件与目录|
|`file.move`|File Move|file|trusted_worker|side_effect|移动文件或目录|
|`file.path_join`|Path Join|file|trusted_worker|pure|拼接并规范化路径|
|`file.rename`|File Rename|file|trusted_worker|side_effect|重命名文件或目录|
|`flow.chat_output`|Chat Output|flow|trusted_service|side_effect|将 Message 或 Variable 作为助手消息推送到聊天会话|
|`flow.if`|If|flow|trusted_service|pure|按受限 Python 表达式选择分支|
|`flow.loop_end`|Loop End|flow|trusted_service|side_effect|收集循环体输出|
|`flow.loop_start`|Loop Start|flow|trusted_service|side_effect|按行、按块或计数启动循环|
|`flow.merge`|Merge|flow|trusted_service|pure|汇合两个可部分到达的表格分支|
|`flow.switch`|Switch|flow|trusted_service|pure|按变量值选择命名分支|
|`flow.trigger`|Trigger|flow|trusted_service|side_effect|手动、聊天、定时、文件或 HTTP 工作流入口|
|`flow.variable`|Variable|flow|trusted_worker|pure|定义流变量|
|`flow.wait`|Wait|flow|trusted_service|side_effect|等待指定秒数并响应取消|
|`table.column_filter`|Column Filter|table|trusted_worker|pure|按名称或通配符筛选列|
|`table.column_rename`|Column Rename|table|trusted_worker|pure|重命名表格列|
|`table.concatenate`|Concatenate|table|trusted_worker|pure|按动态命名输入拼接表格|
|`table.creator`|Table Creator|table|trusted_worker|pure|从参数中的行创建表格|
|`table.duplicate_filter`|Duplicate Filter|table|trusted_worker|pure|按列去重|
|`table.from_variables`|Variables to Table|table|trusted_worker|pure|将选中流变量转换为单行表|
|`table.groupby`|GroupBy|table|trusted_worker|pure|按分组列聚合表格|
|`table.joiner`|Joiner|table|trusted_worker|pure|按指定列连接两个表格|
|`table.math_formula`|Math Formula|table|trusted_worker|pure|用 $列名$ 语法新增计算列|
|`table.missing_value`|Missing Value|table|trusted_worker|pure|按列处理缺失值|
|`table.pivot`|Pivot|table|trusted_worker|pure|将行透视成列|
|`table.polars_expression`|Polars Expression|table|trusted_worker|pure|用 AST 白名单表达式新增列|
|`table.read_csv`|Read CSV|table|trusted_worker|pure|读取 CSV 文件为表格|
|`table.read_json`|Read JSON|table|trusted_worker|pure|读取 JSON 数组或 JSON Lines 文件|
|`table.read_parquet`|Read Parquet|table|trusted_worker|pure|读取 Parquet 文件|
|`table.row_count`|Table Row Count|table|trusted_worker|pure|输出表格行数变量|
|`table.row_filter`|Row Filter|table|trusted_worker|pure|按单条件筛选行|
|`table.sorter`|Sorter|table|trusted_worker|pure|按多个列键稳定排序|
|`table.string_manipulation`|String Manipulation|table|trusted_worker|pure|执行常用字符串函数|
|`table.to_variables`|Table to Variables|table|trusted_worker|pure|将表格行或列转换为流变量|
|`table.type_cast`|Type Cast|table|trusted_worker|pure|转换列的数据类型|
|`table.unpivot`|Unpivot|table|trusted_worker|pure|将列展开成行|
|`table.view`|Table View|table|trusted_worker|pure|在节点内预览输入表格|
|`table.write_csv`|Write CSV|table|trusted_worker|side_effect|将表格写入 CSV 文件|
|`table.write_json`|Write JSON|table|trusted_worker|side_effect|将表格写入 JSON 数组或 JSON Lines|
|`table.write_parquet`|Write Parquet|table|trusted_worker|side_effect|将表格写入 Parquet 文件|

## LLM Call (`agent.llm_call`)

通过主机 LLMProxy 执行流式文本或 JSON 补全

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "llm": {
      "type": "string",
      "description": "命名 LLM 配置"
    },
    "system_prompt": {
      "type": "string",
      "description": "系统提示模板"
    },
    "user_prompt": {
      "type": "string",
      "description": "用户提示模板"
    },
    "table_max_rows": {
      "type": "integer",
      "minimum": 0,
      "description": "表格最大行数"
    },
    "temperature": {
      "type": "number",
      "description": "采样温度"
    },
    "max_tokens": {
      "type": "integer",
      "minimum": 1,
      "description": "最大输出 token"
    },
    "output": {
      "type": "string",
      "enum": [
        "text",
        "json"
      ],
      "description": "输出类型"
    },
    "json_schema": {
      "type": "object",
      "description": "可选 JSON Schema"
    }
  },
  "required": [
    "llm",
    "user_prompt"
  ]
}
```

## Agent Loop (`agent.loop`)

执行可停止、可审计的 ReAct 工具调用循环

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "llm": {
      "type": "string",
      "description": "命名 LLM 配置"
    },
    "system_prompt": {
      "type": "string",
      "description": "系统提示模板"
    },
    "task": {
      "type": "string",
      "description": "任务模板"
    },
    "max_turns": {
      "type": "integer",
      "minimum": 1,
      "description": "最大轮数"
    },
    "on_max_turns": {
      "type": "string",
      "enum": [
        "fail",
        "return_partial"
      ],
      "description": "达到最大轮数时的行为"
    },
    "stop_on_text": {
      "type": "string",
      "description": "优先于工具调用的停止正则"
    },
    "tool_choice": {
      "type": "string",
      "enum": [
        "auto",
        "required"
      ],
      "description": "工具选择"
    },
    "tool_timeout": {
      "type": "number",
      "minimum": 0.001,
      "description": "工具超时秒数"
    }
  },
  "required": [
    "llm",
    "task"
  ]
}
```

## Node as Tool (`agent.node_tool`)

把显式授权的节点包装为受控 Agent 工具

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "target_node": {
      "type": "string",
      "description": "目标节点 ID"
    },
    "tool_name": {
      "type": "string",
      "pattern": "^[A-Za-z_][A-Za-z0-9_]*$",
      "description": "工具名"
    },
    "description": {
      "type": "string",
      "description": "工具用途"
    },
    "exposed_params": {
      "type": "array",
      "description": "允许模型填写的参数白名单"
    },
    "result_format": {
      "type": "string",
      "enum": [
        "table_markdown",
        "json",
        "text"
      ],
      "description": "结果格式"
    },
    "allow_side_effects": {
      "type": "boolean",
      "description": "显式授权副作用"
    },
    "require_confirmation": {
      "type": "boolean",
      "description": "每次调用需要确认"
    },
    "tool_timeout": {
      "type": "number",
      "minimum": 0.001,
      "description": "工具超时秒数"
    }
  },
  "required": [
    "target_node",
    "tool_name",
    "description"
  ]
}
```

## Prompt Template (`agent.prompt_template`)

用受限 Jinja2 模板组合变量与只读表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "template": {
      "type": "string",
      "description": "Jinja2 模板文本"
    },
    "source": {
      "type": "string",
      "enum": [
        "inline",
        "file"
      ],
      "description": "模板来源"
    },
    "path": {
      "type": "string",
      "description": "prompts/*.md 模板路径"
    },
    "role": {
      "type": "string",
      "enum": [
        "system",
        "user"
      ],
      "description": "消息角色"
    },
    "table_max_rows": {
      "type": "integer",
      "minimum": 0,
      "description": "表格最大行数"
    }
  },
  "required": [
    "template"
  ]
}
```

## Python Script (`code.python`)

在可信 Worker 中执行用户 Python 代码

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "source": {
      "type": "string",
      "description": "代码来源",
      "enum": [
        "inline",
        "file"
      ],
      "default": "inline"
    },
    "code": {
      "type": "string",
      "description": "内联代码"
    },
    "path": {
      "type": "string",
      "description": "代码文件路径"
    },
    "inputs": {
      "type": "array",
      "description": "输入端口映射",
      "default": []
    },
    "outputs": {
      "type": "array",
      "description": "输出端口声明",
      "default": []
    }
  },
  "required": []
}
```

## Excel Cell Update (`excel.cell_update`)

原子更新若干不连续单元格，默认禁止公式

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "sheet": {
      "type": "string",
      "description": "目标工作表"
    },
    "cells": {
      "type": "array",
      "description": "单元格地址与值列表"
    },
    "allow_formula": {
      "type": "boolean",
      "description": "是否允许公式"
    }
  },
  "required": [
    "sheet"
  ]
}
```

## Excel Connect (`excel.connect`)

连接可见 Excel 或创建独立的可见/隐藏实例

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "attach_visible",
        "new_visible",
        "new_hidden"
      ],
      "description": "连接模式"
    },
    "target": {
      "type": "object",
      "description": "稳定工作簿/路径及显式 PID 选择提示",
      "properties": {
        "workbook": {
          "type": "string",
          "description": "工作簿名"
        },
        "path": {
          "type": "string",
          "description": "工作簿完整路径"
        },
        "pid": {
          "type": "integer",
          "description": "显式实例 PID"
        },
        "window_title": {
          "type": "string",
          "description": "窗口标题提示"
        }
      }
    },
    "on_finish": {
      "type": "string",
      "enum": [
        "save",
        "discard"
      ],
      "description": "隐藏实例结束时的显式保存或放弃选择"
    }
  },
  "required": [
    "mode"
  ]
}
```

## Excel Read Range (`excel.read_range`)

实时读取 Excel 区域、表对象或命名区域为表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "sheet": {
      "type": "string",
      "description": "工作表名"
    },
    "range": {
      "type": "string",
      "description": "A1 区域、表对象或命名区域；空为 UsedRange"
    },
    "header": {
      "type": "boolean",
      "description": "首行为表头"
    },
    "dtype_hints": {
      "type": "object",
      "description": "按列指定 Arrow 类型"
    }
  },
  "required": [
    "sheet"
  ]
}
```

## Excel Save (`excel.save`)

显式保存或另存工作簿，不隐式覆盖文件

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "save",
        "save_as"
      ],
      "description": "保存方式"
    },
    "path": {
      "type": "string",
      "description": "相对 Root 的另存路径"
    },
    "format": {
      "type": "string",
      "enum": [
        "xlsx",
        "xlsm",
        "csv"
      ],
      "description": "文件格式"
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否允许覆盖已有文件"
    }
  },
  "required": [
    "mode"
  ]
}
```

## Excel Sheet (`excel.sheet`)

创建、删除、重命名或清空工作表

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": [
        "create",
        "delete",
        "rename",
        "clear"
      ],
      "description": "工作表操作"
    },
    "name": {
      "type": "string",
      "description": "原工作表名"
    },
    "new_name": {
      "type": "string",
      "description": "重命名目标"
    }
  },
  "required": [
    "action",
    "name"
  ]
}
```

## Excel Sheet Names (`excel.sheet_names`)

列出工作表名、索引与可见状态

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {},
  "required": []
}
```

## Excel Workbook (`excel.workbook`)

引用已打开工作簿、打开文件或新建工作簿

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "open_existing",
        "open_file",
        "new"
      ],
      "description": "工作簿获取方式"
    },
    "name": {
      "type": "string",
      "description": "已打开工作簿名"
    },
    "path": {
      "type": "string",
      "description": "相对 Root 的工作簿文件路径"
    }
  },
  "required": [
    "mode"
  ]
}
```

## Excel Write Table (`excel.write_table`)

整块写入、追加或覆盖 Excel 工作表区域

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "sheet": {
      "type": "string",
      "description": "目标工作表"
    },
    "start": {
      "type": "string",
      "description": "起始单元格"
    },
    "mode": {
      "type": "string",
      "enum": [
        "overwrite",
        "append"
      ],
      "description": "写入模式"
    },
    "header": {
      "type": "boolean",
      "description": "是否写表头"
    },
    "clear_below": {
      "type": "boolean",
      "description": "覆盖前清空下方旧内容"
    },
    "allow_formula": {
      "type": "boolean",
      "description": "是否允许公式字符串"
    },
    "autofit": {
      "type": "boolean",
      "description": "写后自适应列宽"
    },
    "preserve_format": {
      "type": "boolean",
      "description": "保留目标格式"
    },
    "fast_mode": {
      "type": "boolean",
      "description": "临时关闭刷新、事件和自动计算"
    }
  },
  "required": [
    "sheet",
    "start",
    "mode"
  ]
}
```

## File Copy (`file.copy`)

复制文件或目录

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "单文件路径"
    },
    "target": {
      "type": "string",
      "description": "目标路径"
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否覆盖",
      "default": false
    },
    "permanent": {
      "type": "boolean",
      "description": "是否永久删除",
      "default": false
    }
  },
  "required": []
}
```

## File Delete (`file.delete`)

移入回收站或永久删除

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "单文件路径"
    },
    "target": {
      "type": "string",
      "description": "目标路径"
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否覆盖",
      "default": false
    },
    "permanent": {
      "type": "boolean",
      "description": "是否永久删除",
      "default": false
    }
  },
  "required": []
}
```

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

## File Move (`file.move`)

移动文件或目录

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "单文件路径"
    },
    "target": {
      "type": "string",
      "description": "目标路径"
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否覆盖",
      "default": false
    },
    "permanent": {
      "type": "boolean",
      "description": "是否永久删除",
      "default": false
    }
  },
  "required": []
}
```

## Path Join (`file.path_join`)

拼接并规范化路径

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "parts": {
      "type": "array",
      "description": "路径片段"
    }
  },
  "required": [
    "parts"
  ]
}
```

## File Rename (`file.rename`)

重命名文件或目录

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "单文件路径"
    },
    "target": {
      "type": "string",
      "description": "目标路径"
    },
    "overwrite": {
      "type": "boolean",
      "description": "是否覆盖",
      "default": false
    },
    "permanent": {
      "type": "boolean",
      "description": "是否永久删除",
      "default": false
    }
  },
  "required": []
}
```

## Chat Output (`flow.chat_output`)

将 Message 或 Variable 作为助手消息推送到聊天会话

```json
{
  "type": "object",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {}
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

## Loop End (`flow.loop_end`)

收集循环体输出

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "loop_id": {
      "type": "string",
      "description": "Loop Start 配对标识"
    },
    "mode": {
      "type": "string",
      "enum": [
        "concat",
        "last",
        "variables"
      ],
      "description": "收集模式"
    },
    "on_error": {
      "type": "string",
      "enum": [
        "fail",
        "skip"
      ],
      "description": "迭代失败策略"
    }
  },
  "required": [
    "loop_id",
    "mode"
  ]
}
```

## Loop Start (`flow.loop_start`)

按行、按块或计数启动循环

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "mode": {
      "type": "string",
      "enum": [
        "row",
        "chunk",
        "counting"
      ],
      "description": "循环模式"
    },
    "loop_id": {
      "type": "string",
      "description": "Loop End 配对标识"
    },
    "chunk_size": {
      "type": "integer",
      "minimum": 1,
      "description": "每块行数"
    },
    "from": {
      "type": "integer",
      "description": "计数起点"
    },
    "to": {
      "type": "integer",
      "description": "计数排他上界"
    },
    "step": {
      "type": "integer",
      "description": "计数步长"
    }
  },
  "required": [
    "mode",
    "loop_id"
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

## Concatenate (`table.concatenate`)

按动态命名输入拼接表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "input_count": {
      "type": "integer",
      "description": "输入端口数量",
      "minimum": 2,
      "default": 2
    },
    "how": {
      "type": "string",
      "description": "拼接方式",
      "enum": [
        "vertical",
        "horizontal",
        "diagonal"
      ],
      "default": "vertical"
    }
  },
  "required": []
}
```

## Table Creator (`table.creator`)

从参数中的行创建表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "rows": {
      "type": "array",
      "description": "表格行数据"
    }
  },
  "required": [
    "rows"
  ]
}
```

## Duplicate Filter (`table.duplicate_filter`)

按列去重

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "columns": {
      "type": "array",
      "description": "去重列，空为全部",
      "default": []
    },
    "keep": {
      "type": "string",
      "description": "保留项",
      "enum": [
        "first",
        "last"
      ],
      "default": "first"
    }
  },
  "required": []
}
```

## Variables to Table (`table.from_variables`)

将选中流变量转换为单行表

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "names": {
      "type": "array",
      "description": "变量名列表"
    }
  },
  "required": [
    "names"
  ]
}
```

## GroupBy (`table.groupby`)

按分组列聚合表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "group_by": {
      "type": "array",
      "description": "分组列"
    },
    "aggregations": {
      "type": "array",
      "description": "聚合表达式列表"
    }
  },
  "required": [
    "group_by",
    "aggregations"
  ]
}
```

## Joiner (`table.joiner`)

按指定列连接两个表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "how": {
      "type": "string",
      "description": "连接方式",
      "enum": [
        "inner",
        "left",
        "right",
        "outer",
        "cross",
        "anti",
        "semi"
      ]
    },
    "left_on": {
      "type": "string",
      "description": "左表连接列"
    },
    "right_on": {
      "type": "string",
      "description": "右表连接列"
    }
  },
  "required": [
    "how",
    "left_on",
    "right_on"
  ]
}
```

## Math Formula (`table.math_formula`)

用 $列名$ 语法新增计算列

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "formula": {
      "type": "string",
      "description": "计算公式"
    },
    "alias": {
      "type": "string",
      "description": "输出列别名"
    }
  },
  "required": [
    "formula",
    "alias"
  ]
}
```

## Missing Value (`table.missing_value`)

按列处理缺失值

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "strategies": {
      "type": "object",
      "description": "每列的缺失值策略"
    }
  },
  "required": [
    "strategies"
  ]
}
```

## Pivot (`table.pivot`)

将行透视成列

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "index": {
      "type": "array",
      "description": "行索引列"
    },
    "columns": {
      "type": "string",
      "description": "透视列"
    },
    "values": {
      "type": "string",
      "description": "值列"
    },
    "agg": {
      "type": "string",
      "description": "聚合方式"
    }
  },
  "required": [
    "index",
    "columns",
    "values",
    "agg"
  ]
}
```

## Polars Expression (`table.polars_expression`)

用 AST 白名单表达式新增列

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "expressions": {
      "type": "array",
      "description": "表达式与别名列表"
    }
  },
  "required": [
    "expressions"
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

## String Manipulation (`table.string_manipulation`)

执行常用字符串函数

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "column": {
      "type": "string",
      "description": "输入列"
    },
    "operation": {
      "type": "string",
      "description": "字符串操作"
    },
    "args": {
      "type": "array",
      "description": "操作参数",
      "default": []
    },
    "alias": {
      "type": "string",
      "description": "输出列别名"
    }
  },
  "required": [
    "column",
    "operation",
    "alias"
  ]
}
```

## Table to Variables (`table.to_variables`)

将表格行或列转换为流变量

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "row_index": {
      "type": "integer",
      "description": "行索引",
      "default": 0
    },
    "mode": {
      "type": "string",
      "description": "转换模式",
      "enum": [
        "row",
        "column_lists"
      ],
      "default": "row"
    }
  },
  "required": []
}
```

## Type Cast (`table.type_cast`)

转换列的数据类型

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "mapping": {
      "type": "object",
      "description": "列到类型的映射"
    },
    "strict": {
      "type": "boolean",
      "description": "失败是否报错",
      "default": false
    }
  },
  "required": [
    "mapping"
  ]
}
```

## Unpivot (`table.unpivot`)

将列展开成行

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "index": {
      "type": "array",
      "description": "保留索引列"
    },
    "on": {
      "type": "array",
      "description": "展开列"
    },
    "variable_name": {
      "type": "string",
      "description": "变量列名",
      "default": "variable"
    },
    "value_name": {
      "type": "string",
      "description": "值列名",
      "default": "value"
    }
  },
  "required": []
}
```

## Table View (`table.view`)

在节点内预览输入表格

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "rows": {
      "type": "integer",
      "description": "节点内显示行数",
      "default": 10
    }
  },
  "required": []
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
