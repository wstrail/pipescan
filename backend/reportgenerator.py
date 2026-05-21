# -*- coding: utf-8 -*-
"""Generate inspection reports from evaluation results."""

from datetime import datetime
from pathlib import Path
from typing import Any


def _fmt(value: Any) -> str:
    return str(value if value is not None else "")


class ReportGenerator:
    """Convert algorithm output to a readable Markdown inspection report."""

    def generate_markdown(self, evaluation: dict[str, Any]) -> str:
        pipe = evaluation["pipe_info"]
        params = evaluation["parameters"]
        levels = evaluation["levels"]
        defects = evaluation.get("defects", [])

        lines = [
            f"# 管道机器人检测报告 - {pipe.get('pipe_id', '未命名管段')}",
            "",
            f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 管段长度：{pipe.get('pipe_length_m')} m",
            f"- 管径：{pipe.get('diameter_mm')} mm",
            f"- 区域类型：{pipe.get('region_type')}",
            f"- 土质类型：{pipe.get('soil_type')}",
            "",
            "## 评估结论",
            "",
            f"- 结构性缺陷：{levels['structural_defect_level']['level']}，{levels['structural_defect_level']['status']}",
            f"- 功能性缺陷：{levels['functional_defect_level']['level']}，{levels['functional_defect_level']['status']}",
            f"- 修复建议：{levels['repair_level']['level']}，{levels['repair_level']['suggestion']}",
            f"- 养护建议：{levels['maintenance_level']['level']}，{levels['maintenance_level']['suggestion']}",
            "",
            "## 核心指标",
            "",
            "| 指标 | 数值 |",
            "| --- | ---: |",
            f"| F 结构性缺陷参数 | {params['F_structural']} |",
            f"| G 功能性缺陷参数 | {params['G_functional']} |",
            f"| RI 修复指数 | {params['RI_repair_index']} |",
            f"| MI 养护指数 | {params['MI_maintenance_index']} |",
            f"| K 区域重要性 | {params['K_region']} |",
            f"| E 管道重要性 | {params['E_pipe']} |",
            f"| T 土质影响 | {params['T_soil']} |",
            "",
            "## 缺陷明细",
            "",
            "| 序号 | 距离(m) | 类型 | 代码 | 分值 | 长度(m) | 描述 |",
            "| ---: | ---: | --- | --- | ---: | ---: | --- |",
        ]

        if defects:
            for index, defect in enumerate(defects, start=1):
                lines.append(
                    "| {index} | {distance} | {category} | {code} | {score} | {length} | {description} |".format(
                        index=index,
                        distance=_fmt(defect.get("distance_m", 0)),
                        category=_fmt(defect.get("category")),
                        code=_fmt(defect.get("code")),
                        score=_fmt(defect.get("score")),
                        length=_fmt(defect.get("length")),
                        description=_fmt(defect.get("description")),
                    )
                )
        else:
            lines.append("| 1 | 0 | - | - | 0 | 0 | 未记录缺陷 |")

        lines.extend(
            [
                "",
                "## 工程处理建议",
                "",
                f"1. {levels['repair_level']['suggestion']}",
                f"2. {levels['maintenance_level']['suggestion']}",
                "3. 建议将机器人里程、视频帧、缺陷截图与本报告编号关联存档，便于复核。",
            ]
        )

        return "\n".join(lines) + "\n"

    def save_markdown(self, evaluation: dict[str, Any], output_dir: str | Path) -> Path:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        pipe_id = str(evaluation["pipe_info"].get("pipe_id", "pipe")).replace("/", "_").replace("\\", "_")
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{pipe_id}_report.md"
        target = output_path / filename
        target.write_text(self.generate_markdown(evaluation), encoding="utf-8")
        return target
