"""h3_prompt_optimizer 纯逻辑单元测试（分组合并 + 资产去重，不调用 LLM/DB）。"""

import pytest

from app.services.h3_prompt_optimizer import (
    GROUP_MAX_IMAGES,
    _build_group_input,
    _group_segments,
    _group_segments_with_images,
    _seg_duration,
    _select_groups,
)


def _seg(seg_id: int, start: float, end: float, scene: str = "场景A", **extra) -> dict:
    seg = {
        "id": seg_id,
        "start_time": start,
        "end_time": end,
        "scene_name": scene,
        "shot_type": "中景",
        "shot_description": f"镜头{seg_id}描述",
        "dialogue": [],
        "role_view_info": [],
    }
    seg.update(extra)
    return seg


def _role_view(role_name: str) -> dict:
    return {"role_name": role_name, "position": "居中", "action": "端坐",
            "emotion": "严肃", "visibility": "visible"}


class TestGroupSegments:
    def test_script55_like_durations_produce_3_groups(self):
        """脚本 55 的 14 个分镜时长 → 应合并为 3 组（每组 < 15s）。"""
        durations = [2.0, 3.9, 2.5, 2.0, 2.0, 3.6, 3.0, 4.3, 2.5, 2.5, 4.0, 2.0, 2.0, 3.0]
        segments = []
        t = 0.0
        for i, d in enumerate(durations, start=144):
            segments.append(_seg(i, t, t + d))
            t += d

        groups = _group_segments(segments)

        assert len(groups) == 3
        # 组 1：id 144-148，12.4s
        assert [s["id"] for s in groups[0]] == [144, 145, 146, 147, 148]
        assert sum(_seg_duration(s) for s in groups[0]) == pytest.approx(12.4)
        # 组 2：id 149-152，13.4s
        assert [s["id"] for s in groups[1]] == [149, 150, 151, 152]
        assert sum(_seg_duration(s) for s in groups[1]) == pytest.approx(13.4)
        # 组 3：id 153-157，13.5s
        assert [s["id"] for s in groups[2]] == [153, 154, 155, 156, 157]
        assert sum(_seg_duration(s) for s in groups[2]) == pytest.approx(13.5)
        # 所有组时长均 < 15s
        for g in groups:
            assert sum(_seg_duration(s) for s in g) < 15.0

    def test_single_segment_over_threshold_own_group(self):
        """单个分镜时长 >= 15s 时独立成组。"""
        segments = [_seg(1, 0, 20), _seg(2, 20, 25)]
        groups = _group_segments(segments)
        assert len(groups) == 2
        assert [s["id"] for s in groups[0]] == [1]
        assert [s["id"] for s in groups[1]] == [2]

    def test_empty_input(self):
        assert _group_segments([]) == []

    def test_one_segment(self):
        segments = [_seg(1, 0, 5)]
        groups = _group_segments(segments)
        assert len(groups) == 1
        assert [s["id"] for s in groups[0]] == [1]


class TestGroupSegmentsWithImages:
    """按 时长(<15s) + 参考图片数(<=5) 合并分镜。"""

    def _role_images(self, n: int) -> dict[str, dict]:
        return {f"角色{i}": {"id": 100 + i, "role_name": f"角色{i}"} for i in range(1, n + 1)}

    def test_image_cap_splits_group(self):
        """6 个分镜各引用 1 张不同角色图 → 第 6 个分镜触发上限，拆成 2 组。"""
        segments = [
            _seg(i, i * 2.0, i * 2.0 + 2.0, role_view_info=[_role_view(f"角色{i}")])
            for i in range(1, 7)
        ]
        role_images = self._role_images(6)
        groups = _group_segments_with_images(segments, {}, role_images, use_scene_image=False)

        assert len(groups) == 2
        # 组 1 装下前 5 个分镜（5 张参考图，时长 10s < 15s）
        assert [s["id"] for s in groups[0]] == [1, 2, 3, 4, 5]
        assert sum(_seg_duration(s) for s in groups[0]) == 10.0
        # 第 6 个分镜会让参考图变 6 张 > 5 → 独立成组
        assert [s["id"] for s in groups[1]] == [6]

    def test_image_cap_overrides_duration(self):
        """时长远不足 15s 但图片数超限 → 立即收组，不再按 15s 合并。"""
        segments = [
            _seg(i, i * 1.0, i * 1.0 + 1.0, role_view_info=[_role_view(f"角色{i}")])
            for i in range(1, 7)
        ]
        role_images = self._role_images(6)
        groups = _group_segments_with_images(segments, {}, role_images, use_scene_image=False)

        # 总时长仅 6s，仍因图片上限拆成 2 组
        assert len(groups) == 2
        assert [s["id"] for s in groups[0]] == [1, 2, 3, 4, 5]
        assert [s["id"] for s in groups[1]] == [6]

    def test_same_asset_not_counted_twice(self):
        """相同角色图跨分镜出现只算 1 张 → 不触发上限，正常按时长合并。"""
        # 4 个分镜全部引用同一张角色图
        segments = [
            _seg(i, i * 2.0, i * 2.0 + 2.0, role_view_info=[_role_view("同一个人")])
            for i in range(1, 5)
        ]
        role_images = {"同一个人": {"id": 200, "role_name": "同一个人"}}
        groups = _group_segments_with_images(segments, {}, role_images, use_scene_image=False)

        assert len(groups) == 1
        assert [s["id"] for s in groups[0]] == [1, 2, 3, 4]

    def test_single_segment_over_image_cap_own_group(self):
        """单个分镜自身引用超过 5 张图 → 无法拆分，独立成组。"""
        segments = [_seg(1, 0, 2.0, role_view_info=[_role_view(f"角色{i}") for i in range(1, 7)])]
        role_images = self._role_images(6)
        groups = _group_segments_with_images(segments, {}, role_images, use_scene_image=False)

        assert len(groups) == 1
        assert [s["id"] for s in groups[0]] == [1]

    def test_scene_images_count_with_flag(self):
        """use_scene_image=True 时场景图计入参考图数量，触发上限拆分。"""
        # 5 个分镜各引用 1 张不同角色图 + 各自不同场景图
        segments = [
            _seg(i, i * 1.0, i * 1.0 + 1.0, scene=f"场景{i}",
                 role_view_info=[_role_view(f"角色{i}")])
            for i in range(1, 6)
        ]
        role_images = self._role_images(5)
        scene_images = {f"场景{i}": {"id": 300 + i, "scene_name": f"场景{i}"} for i in range(1, 6)}

        # 不带场景图：5 张角色图，未超限 → 1 组
        groups_no_scene = _group_segments_with_images(
            segments, scene_images, role_images, use_scene_image=False
        )
        assert len(groups_no_scene) == 1

        # 带场景图：5 角色 + 5 场景 = 10 张 → 第 2 个分镜就超限
        groups_with_scene = _group_segments_with_images(
            segments, scene_images, role_images, use_scene_image=True
        )
        assert len(groups_with_scene) >= 2
        # 每个组的参考图都不超过上限
        for g in groups_with_scene:
            pic_ids = set()
            for s in g:
                pic_ids.update(
                    [("scene", scene_images[s["scene_name"]]["id"])]
                    if s["scene_name"] in scene_images else []
                )
                pic_ids.update(
                    ("role", role_images[v["role_name"]]["id"])
                    for v in s.get("role_view_info") or []
                    if v["role_name"] in role_images
                )
            assert len(pic_ids) <= GROUP_MAX_IMAGES


class TestSelectGroups:
    """merge_segments 开关：True 合并，False 每分镜独立成组。"""

    def test_merge_true_uses_merge_logic(self):
        segments = [
            _seg(i, i * 2.0, i * 2.0 + 2.0, role_view_info=[_role_view(f"角色{i}")])
            for i in range(1, 7)
        ]
        role_images = {f"角色{i}": {"id": 100 + i, "role_name": f"角色{i}"} for i in range(1, 7)}
        groups = _select_groups(segments, {}, role_images, use_scene_image=False, merge_segments=True)
        # 图片上限 5 触发拆分
        assert len(groups) == 2
        assert [s["id"] for s in groups[0]] == [1, 2, 3, 4, 5]
        assert [s["id"] for s in groups[1]] == [6]

    def test_merge_false_each_segment_own_group(self):
        """默认 merge_segments=False：不合并，每个分镜独立成组。"""
        segments = [_seg(i, i * 2.0, i * 2.0 + 2.0) for i in range(1, 5)]
        groups = _select_groups(segments, {}, {}, use_scene_image=False, merge_segments=False)
        assert len(groups) == 4
        for g in groups:
            assert len(g) == 1
        assert [g[0]["id"] for g in groups] == [1, 2, 3, 4]

    def test_merge_false_empty_input(self):
        assert _select_groups([], {}, {}, use_scene_image=False, merge_segments=False) == []


class TestBuildGroupInput:
    def _group_with_assets(self):
        """两个分镜：共享同一场景图 + 同一角色图，角色状态重复出现。"""
        group = [
            _seg(
                1, 0.0, 2.0, scene="秦殿",
                dialogue=[{"role_name": "秦王", "lines": "第一句", "audio_style": "威严"}],
                role_view_info=[
                    {"role_name": "秦王", "position": "居中", "action": "端坐", "emotion": "严肃",
                     "visibility": "visible"},
                    {"role_name": "旁白", "visibility": "off_screen"},
                ],
            ),
            _seg(
                2, 2.0, 5.0, scene="秦殿",
                dialogue=[{"role_name": "秦王", "lines": "第二句", "audio_style": "威严"}],
                role_view_info=[
                    {"role_name": "秦王", "position": "居中", "action": "端坐", "emotion": "严肃",
                     "visibility": "visible"},
                    {"role_name": "武将", "position": "左下", "action": "抱拳", "emotion": "恭敬",
                     "visibility": "visible"},
                ],
            ),
        ]
        scene_images = {"秦殿": {"id": 10, "scene_name": "秦殿",
                                 "path": "/data/scenes/秦殿.png"}}
        role_images = {"秦王": {"id": 20, "role_name": "秦王", "path": "/data/roles/秦王.png"},
                       "武将": {"id": 21, "role_name": "武将", "path": "/data/roles/武将.png"}}
        return group, scene_images, role_images

    def test_picture_dedup_and_relative_time(self):
        group, scene_images, role_images = self._group_with_assets()
        input_json, image_map = _build_group_input(
            group, scene_images, role_images, use_scene_image=True
        )

        # 时长预算 = 组总时长
        assert input_json["duration_budget"] == 5.0
        # 两个镜头，时间换算为组内相对时间（第一镜从 0 开始）
        assert len(input_json["shots"]) == 2
        assert input_json["shots"][0]["start_time"] == 0.0
        assert input_json["shots"][0]["end_time"] == 2.0
        assert input_json["shots"][1]["start_time"] == 2.0
        assert input_json["shots"][1]["end_time"] == 5.0

        # 场景图：两个镜头同一场景 → 只引用一次
        assert input_json["refer_image"].count("场景参考 <Picture") == 1
        assert "场景参考 <Picture 1>（秦殿）" in input_json["refer_image"]

        # 角色图：秦王在两只镜头都可见 → 只引用一次；武将新出现 → 引用一次
        assert input_json["refer_image"].count("角色参考 <Picture") == 2
        assert "角色参考 <Picture 2>（秦王）" in input_json["refer_image"]
        assert "角色参考 <Picture 3>（武将）" in input_json["refer_image"]

        # image_map 与 refer_image 一致（3 张不重复图片，值直接是图片路径）
        assert len(image_map) == 3
        assert image_map[0] == {"Picture 1": "/data/scenes/秦殿.png"}
        assert image_map[1] == {"Picture 2": "/data/roles/秦王.png"}
        assert image_map[2] == {"Picture 3": "/data/roles/武将.png"}

    def test_role_state_dedup(self):
        group, scene_images, role_images = self._group_with_assets()
        input_json, _ = _build_group_input(
            group, scene_images, role_images, use_scene_image=True
        )

        # 秦王两镜状态完全一致 → 只在第一镜出现；武将只在第二镜出现
        assert len(input_json["shots"][0]["role_view_info"]) == 1
        assert input_json["shots"][0]["role_view_info"][0]["role_name"] == "秦王"
        assert len(input_json["shots"][1]["role_view_info"]) == 1
        assert input_json["shots"][1]["role_view_info"][0]["role_name"] == "武将"

    def test_use_scene_image_false_default_excludes_scene(self):
        """默认 use_scene_image=False：场景图不作为参考输入。"""
        group, scene_images, role_images = self._group_with_assets()
        input_json, image_map = _build_group_input(group, scene_images, role_images)

        # refer_image 不含场景参考，只含角色参考
        assert "场景参考" not in input_json.get("refer_image", "")
        assert "角色参考 <Picture 1>（秦王）" in input_json["refer_image"]
        assert "角色参考 <Picture 2>（武将）" in input_json["refer_image"]

        # image_map 只有角色图，没有场景图（值直接是图片路径）
        assert len(image_map) == 2
        assert image_map[0] == {"Picture 1": "/data/roles/秦王.png"}
        assert image_map[1] == {"Picture 2": "/data/roles/武将.png"}

        # 场景名仍以文字保留在 shots 中
        assert input_json["shots"][0]["scene_name"] == "秦殿"

    def test_use_scene_image_true_includes_scene(self):
        """use_scene_image=True：场景图作为参考输入，且跨镜头去重。"""
        group, scene_images, role_images = self._group_with_assets()
        input_json, image_map = _build_group_input(
            group, scene_images, role_images, use_scene_image=True
        )

        # 两个镜头同一场景 → refer_image 只出现一次场景参考
        assert input_json["refer_image"].count("场景参考 <Picture") == 1
        assert "场景参考 <Picture 1>（秦殿）" in input_json["refer_image"]
        # 角色图编号顺延
        assert "角色参考 <Picture 2>（秦王）" in input_json["refer_image"]
        assert "角色参考 <Picture 3>（武将）" in input_json["refer_image"]
        # image_map 3 张：场景 + 2 角色（值直接是图片路径）
        assert len(image_map) == 3
        assert image_map[0] == {"Picture 1": "/data/scenes/秦殿.png"}
        assert image_map[1] == {"Picture 2": "/data/roles/秦王.png"}
        assert image_map[2] == {"Picture 3": "/data/roles/武将.png"}

    def test_dialogue_all_kept(self):
        group, scene_images, role_images = self._group_with_assets()
        input_json, _ = _build_group_input(group, scene_images, role_images)

        # 台词是脚本内容，全部保留
        all_lines = [d["lines"] for shot in input_json["shots"] for d in shot["dialogue"]]
        assert all_lines == ["第一句", "第二句"]

    def test_off_screen_role_not_in_role_view(self):
        """visibility != visible 的角色不进入 role_view_info（画外音）。"""
        group, scene_images, role_images = self._group_with_assets()
        input_json, _ = _build_group_input(group, scene_images, role_images)
        for shot in input_json["shots"]:
            for rv in shot["role_view_info"]:
                assert rv["role_name"] != "旁白"

    def test_dialogue_carries_audio_timeline_fields(self):
        """对口型/跨镜长台词：dialogue 需携带 lines_flag / start_offset / end_offset。"""
        group, scene_images, role_images = self._group_with_assets()
        # 头镜台词带跨镜信息，供 LLM 对齐音频切片与 <scenetrans> 续接
        group[0]["dialogue"][0].update(
            {"lines_flag": "head", "start_offset": 0.0, "end_offset": 2.0}
        )
        input_json, _ = _build_group_input(group, scene_images, role_images)
        d = input_json["shots"][0]["dialogue"][0]
        assert d["lines_flag"] == "head"
        assert d["start_offset"] == 0.0
        assert d["end_offset"] == 2.0
        assert d["role_name"] == "秦王" and d["lines"] == "第一句" and d["audio_style"] == "威严"
