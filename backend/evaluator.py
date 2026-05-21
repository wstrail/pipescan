# -*- coding: utf-8 -*-
"""Pipe defect evaluation algorithm.

The formulas are intentionally isolated from web/API code so the same logic can
be reused by batch jobs, hardware callbacks, tests, or a future database layer.
"""

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Defect:
    """Single defect detected by the robot or entered by an engineer."""

    category: str
    code: str
    score: float
    length: float = 0.0
    distance_m: float = 0.0
    description: str = ""


class PipeDefectEvaluator:
    """Evaluate structural and functional risk for one pipe segment."""

    REGION_IMPORTANCE_K = {
        "central": 10,
        "traffic": 6,
        "normal": 3,
        "other": 0,
    }

    SOIL_INFLUENCE_T = {
        "weak": 10,
        "medium": 6,
        "strong": 3,
        "unknown": 5,
    }

    @staticmethod
    def get_pipe_importance_e(diameter_mm: float, f_value: float) -> float:
        if diameter_mm > 1500:
            return 10
        if 1000 <= diameter_mm <= 1500:
            return 6
        if 600 <= diameter_mm < 1000 and f_value >= 4:
            return 3
        return 0

    @staticmethod
    def get_level_by_value(value: float) -> dict[str, str]:
        if value < 1:
            return {
                "level": "I级",
                "status": "基本完好",
                "suggestion": "按常规周期巡检。",
            }
        if value < 3:
            return {
                "level": "II级",
                "status": "轻度缺陷",
                "suggestion": "加强观察，结合下一次检测结果决定是否处理。",
            }
        if value < 6:
            return {
                "level": "III级",
                "status": "中度缺陷",
                "suggestion": "建议制定维修或养护计划，并安排复核。",
            }
        return {
            "level": "IV级",
            "status": "严重缺陷",
            "suggestion": "建议尽快处置；必要时采取限流、封堵或应急维修措施。",
        }

    @staticmethod
    def get_repair_level_by_ri(ri: float) -> dict[str, str]:
        if ri < 1:
            return {"level": "I级", "status": "无需修复", "suggestion": "结构条件基本稳定。"}
        if ri < 4:
            return {"level": "II级", "status": "计划修复", "suggestion": "纳入计划修复清单。"}
        if ri < 7:
            return {"level": "III级", "status": "尽快修复", "suggestion": "建议尽快安排局部或整体修复。"}
        return {"level": "IV级", "status": "紧急修复", "suggestion": "建议立即复核并启动应急修复。"}

    @staticmethod
    def get_maintenance_level_by_mi(mi: float) -> dict[str, str]:
        if mi < 1:
            return {"level": "I级", "status": "无需养护", "suggestion": "按常规周期巡检。"}
        if mi < 4:
            return {"level": "II级", "status": "计划养护", "suggestion": "纳入计划清淤、疏通或养护。"}
        if mi < 7:
            return {"level": "III级", "status": "重点养护", "suggestion": "建议尽快清淤、疏通或处理功能性问题。"}
        return {"level": "IV级", "status": "紧急养护", "suggestion": "建议立即处理，避免影响排水能力。"}

    @staticmethod
    def calculate_defect_parameter(defects: list[Defect], pipe_length: float) -> float:
        """Calculate structural F or functional G.

        Severe single defects dominate the result. Mild defects are accumulated
        with length weighting so long continuous defects are not undercounted.
        """

        if not defects:
            return 0.0

        pipe_length = max(pipe_length, 1.0)
        s_max = max(defect.score for defect in defects)
        if s_max > 3:
            long_defect_boost = max(
                0.0,
                max((defect.length / pipe_length) for defect in defects if defect.length > 0) - 0.05,
            )
            return round(min(10.0, s_max + long_defect_boost * 3), 2)

        weighted_sum = 0.0
        for defect in defects:
            length = defect.length if defect.length > 0 else 1.0
            if length <= 1.0:
                weight = 1.0
            elif length <= 1.5:
                weight = 1.5
            else:
                weight = max(1.5, length / pipe_length * 10)
            weighted_sum += defect.score * weight

        return round(min(10.0, weighted_sum / max(s_max, 0.1)), 2)

    def evaluate(
        self,
        pipe_length: float,
        diameter_mm: float,
        defects: list[Defect],
        region_type: str = "normal",
        soil_type: str = "unknown",
        pipe_id: str = "未命名管段",
    ) -> dict[str, Any]:
        structural_defects = [d for d in defects if d.category == "structural"]
        functional_defects = [d for d in defects if d.category == "functional"]

        f_value = self.calculate_defect_parameter(structural_defects, pipe_length)
        g_value = self.calculate_defect_parameter(functional_defects, pipe_length)
        k_value = self.REGION_IMPORTANCE_K.get(region_type, 3)
        e_value = self.get_pipe_importance_e(diameter_mm, f_value)
        t_value = self.SOIL_INFLUENCE_T.get(soil_type, 5)

        ri = round(0.7 * f_value + 0.1 * k_value + 0.05 * e_value + 0.15 * t_value, 2)
        mi = round(0.8 * g_value + 0.15 * k_value + 0.05 * e_value, 2)

        return {
            "pipe_info": {
                "pipe_id": pipe_id,
                "pipe_length_m": pipe_length,
                "diameter_mm": diameter_mm,
                "region_type": region_type,
                "soil_type": soil_type,
            },
            "parameters": {
                "F_structural": f_value,
                "G_functional": g_value,
                "K_region": k_value,
                "E_pipe": e_value,
                "T_soil": t_value,
                "RI_repair_index": ri,
                "MI_maintenance_index": mi,
            },
            "levels": {
                "structural_defect_level": self.get_level_by_value(f_value),
                "functional_defect_level": self.get_level_by_value(g_value),
                "repair_level": self.get_repair_level_by_ri(ri),
                "maintenance_level": self.get_maintenance_level_by_mi(mi),
            },
            "defects": [asdict(defect) for defect in defects],
        }
