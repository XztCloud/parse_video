"""runninghub H3 音驱分镜的音频切片 + 旁白合入逻辑单测（纯逻辑，不触库）。"""
import os

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from app.services.clone_segment_video import AudioOverlay, build_segment_group_audio_package, overlay_narration_audio
from app.util import get_md5


@pytest.fixture()
def audio_factory(tmp_path):
    def _make(seconds: float, name: str) -> str:
        path = str(tmp_path / name)
        Sine(440).to_audio_segment(duration=seconds * 1000).export(path, format="mp3")
        return path
    return _make


def _seg(sid, start, end, dialogue, role_view):
    return {
        "id": sid, "start_time": start, "end_time": end,
        "dialogue": dialogue, "role_view_info": role_view,
    }


def _line(role, lines, flag, s, e, path, style="威严"):
    return {
        "role_name": role, "lines": lines, "audio_style": style,
        "lines_flag": flag, "start_offset": s, "end_offset": e, "audio_path": path,
    }


class TestBuildSegmentGroupAudioPackage:
    def test_long_sentence_across_shots_slices_each_shot(self, audio_factory, tmp_path):
        """镜像 sync_segment_timeline 校准规则：head 镜吃满整句剩余，tail 镜只铺衔接垫。
        用户示例：10s 句跨两镜 → head 镜 (0,10)，tail 镜续接 (10, 0.5 衔接垫)。"""
        s = audio_factory(10.0, "sentence_a.mp3")
        seg1 = _seg(1, 0.0, 6.0, [_line("大王", "长句", "head", 0.0, 6.0, s)],
                    [{"role_name": "大王", "visibility": "visible"}])
        seg2 = _seg(2, 6.0, 10.0, [_line("大王", "长句", "tail", 0.0, 4.0, s)],
                    [{"role_name": "大王", "visibility": "visible"}])

        ref1, _ = build_segment_group_audio_package([seg1, seg2], [1], {}, str(tmp_path))
        ref2, _ = build_segment_group_audio_package([seg1, seg2], [2], {}, str(tmp_path))

        # head 镜吃满整句 (0,10)；tail 镜只铺 0.5s 衔接垫 (10, 0.5)
        assert ref1 == (s, 0.0, 10.0)
        assert ref2 == (s, 10.0, 0.5)

    def test_head_shot_ends_before_sentence_finishes_continues(self, audio_factory, tmp_path):
        """句A 5.04s、head 镜铺满整句后，tail 镜铺句尾接续（衔接垫 0.5s，不消耗整句）。"""
        s = audio_factory(5.04, "sentence_a.mp3")
        seg1 = _seg(1, 0.0, 5.34, [_line("女生", "长句", "head", 0.0, 3.0, s)],
                    [{"role_name": "女生", "visibility": "visible"}])
        seg2 = _seg(2, 5.34, 6.34, [_line("女生", "长句", "tail", 0.0, 1.9, s)],
                    [{"role_name": "女生", "visibility": "visible"}])

        vd = {("女生", "威严", get_md5("长句")): 5.04}
        ref1, _ = build_segment_group_audio_package([seg1, seg2], [1], vd, str(tmp_path))
        ref2, _ = build_segment_group_audio_package([seg1, seg2], [2], vd, str(tmp_path))

        # head 镜吃满整句 5.04；tail 镜从句尾位置铺 0.5s 衔接垫
        assert ref1 == (s, 0.0, 5.04)
        assert ref2 == (s, 5.04, 0.5)

    def test_narration_excluded_from_ref_and_collected_for_overlay(self, audio_factory, tmp_path):
        """旁白不写入口型参考音频；生成后由 overlays 合入（按真实音频流动）。"""
        narration = audio_factory(3.0, "narration.mp3")
        lip = audio_factory(2.0, "lip.mp3")
        seg = _seg(3, 10.0, 15.0,
                   [_line("旁白", "旁白句", "all", 0.0, 3.0, narration),
                    _line("大臣", "臣句", "all", 3.0, 5.0, lip)],
                   [{"role_name": "旁白", "visibility": "invisible"},
                    {"role_name": "大臣", "visibility": "visible"}])

        ref, overlays = build_segment_group_audio_package([seg], [3], {}, str(tmp_path))

        # ref = 口型台词的完整音频 + 其可闻切片；overlays = 旁白切片
        assert ref == (lip, 0.0, 2.0)
        assert len(overlays) == 1
        assert overlays[0][0] == narration and overlays[0][1] == 0.0 and overlays[0][2] == 3.0

    def test_multi_lip_line_merged_to_single_file(self, audio_factory, tmp_path):
        """≥2 条口型台词 → 拼合为镜内完整音频，时长≈镜长。"""
        a = audio_factory(3.0, "a.mp3")
        b = audio_factory(3.0, "b.mp3")
        seg = _seg(4, 15.0, 21.0,
                   [_line("大臣", "一句", "all", 0.0, 3.0, a),
                    _line("大王", "二句", "all", 3.0, 6.0, b)],
                   [{"role_name": "大臣", "visibility": "visible"},
                    {"role_name": "大王", "visibility": "visible"}])

        ref, overlays = build_segment_group_audio_package([seg], [4], {}, str(tmp_path))

        assert os.path.isfile(ref[0])
        assert ref[1] == 0.0
        assert abs(ref[2] - 6.0) < 0.2

    def test_narration_only_group_uses_narration_as_ref(self, audio_factory, tmp_path):
        """纯旁白组：旁白直接作参考音轨（画外音不驱动口型），生成后不再重复合入。"""
        narration = audio_factory(3.0, "narration.mp3")
        seg = _seg(5, 20.0, 24.0,
                   [_line("旁白", "纯旁白", "all", 0.0, 2.0, narration)],
                   [{"role_name": "旁白", "visibility": "invisible"}])

        ref, overlays = build_segment_group_audio_package([seg], [5], {}, str(tmp_path))

        assert ref is not None and ref.start == 0.0
        assert abs(ref.duration - 4.0) < 0.2  # 整组铺轨，全长
        assert os.path.isfile(ref.path)
        assert overlays == []  # 已作参考音轨，不再生成后合入

    def test_no_dialogue_group_gets_quiet_noise_bed(self, audio_factory, tmp_path):
        """纯空镜组：-60dB 噪底兜底（纯数字静音会使 H3 音频 VAE 崩溃）。"""
        seg = _seg(6, 30.0, 34.0, [], [])

        ref, overlays = build_segment_group_audio_package([seg], [6], {}, str(tmp_path))

        assert ref is not None and ref.start == 0.0
        assert abs(ref.duration - 4.0) < 0.2
        assert os.path.isfile(ref.path)
        assert overlays == []
        # 噪底非全零：-60dB 增益后的静音底有极小幅度
        from pydub import AudioSegment
        bed = AudioSegment.from_file(ref.path)
        assert bed.max_dBFS < -55  # 人耳不可闻，但非全零


class TestOverlayNarrationAudio:
    def test_overlay_preserves_video_duration(self, tmp_path, audio_factory):
        import subprocess
        base = str(tmp_path / "base.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=2",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-shortest", base],
            check=True, capture_output=True,
        )
        nar = audio_factory(1.0, "nar.mp3")
        out = str(tmp_path / "out.mp4")

        overlay_narration_audio(base, [AudioOverlay(nar, 0.0, 1.0, 0.5)], out)

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
            capture_output=True, text=True, check=True,
        )
        assert abs(float(probe.stdout.strip()) - 2.0) < 0.2

    def test_empty_overlay_copies(self, tmp_path):
        import shutil
        src = str(tmp_path / "a.mp4")
        dst = str(tmp_path / "b.mp4")
        with open(src, "w") as f:
            f.write("x")
        overlay_narration_audio(src, [], dst)
        assert os.path.isfile(dst)