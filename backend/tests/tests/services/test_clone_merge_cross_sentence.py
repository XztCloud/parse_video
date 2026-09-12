"""跨句音频修复的单测：跨镜句检测（纯逻辑，不触库）。"""
from app.services.clone_merge_video import find_multi_shot_sentences
from app.util import get_md5


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


class TestFindMultiShotSentences:
    def test_sentence_across_multiple_shots_detected(self):
        """句C：head 在 seg270、body/tail 在 271/272 → 贯穿多个分镜，铺放起点 8.2。"""
        c = "/audio/c.mp3"
        segs = [
            _seg(270, 8.2, 14.74, [_line("女生", "句C", "head", 0.0, 2.0, c)],
                 [{"role_name": "女生", "visibility": "visible"}]),
            _seg(271, 14.74, 15.74, [_line("女生", "句C", "body", 0.0, 4.0, c)],
                 [{"role_name": "女生", "visibility": "visible"}]),
            _seg(272, 15.74, 16.74, [_line("女生", "句C", "tail", 0.0, 2.2, c)],
                 [{"role_name": "女生", "visibility": "visible"}]),
        ]
        vd = {("女生", "威严", get_md5("句C")): 6.24}
        sents = find_multi_shot_sentences(segs, vd)
        assert len(sents) == 1
        assert sents[0]["path"] == c
        assert sents[0]["merged_start"] == 8.2
        assert sents[0]["duration"] == 6.24  # 文件不存在时回落估值时长
        assert sents[0]["cover_len"] == 8.54  # 覆盖到 272 镜尾 (16.74 - 8.2)

    def test_sentence_within_single_shot_not_detected(self):
        """句A：head/tail 都出现在同一分镜 → 单镜句子，不替换。"""
        a = "/audio/a.mp3"
        segs = [
            _seg(267, 0.0, 5.34,
                 [_line("女生", "句A", "head", 0.0, 3.0, a),
                  _line("女生", "句A", "tail", 3.0, 4.9, a)],
                 [{"role_name": "女生", "visibility": "visible"}]),
        ]
        vd = {("女生", "威严", get_md5("句A")): 5.04}
        assert find_multi_shot_sentences(segs, vd) == []

    def test_single_shot_all_line_not_detected(self):
        """all 行单镜完成 → 不替换。"""
        b = "/audio/b.mp3"
        segs = [_seg(269, 6.34, 8.2, [_line("女生", "句B", "all", 0.0, 1.0, b)],
                     [{"role_name": "女生", "visibility": "visible"}])]
        vd = {("女生", "威严", get_md5("句B")): 1.56}
        assert find_multi_shot_sentences(segs, vd) == []

    def test_narration_not_detected(self):
        """旁白句子跨镜不处理（旁白在参考轨里本来就是整句连续）。"""
        n = "/audio/n.mp3"
        segs = [
            _seg(1, 0.0, 4.0, [_line("旁白", "旁白句", "all", 0.0, 2.0, n)],
                 [{"role_name": "旁白", "visibility": "invisible"}]),
            _seg(2, 4.0, 8.0, [_line("旁白", "旁白句", "tail", 0.0, 1.0, n)],
                 [{"role_name": "旁白", "visibility": "invisible"}]),
        ]
        vd = {("旁白", "威严", get_md5("旁白句")): 3.0}
        assert find_multi_shot_sentences(segs, vd) == []

    def test_multiple_sentences_detected(self):
        """句A(0s) 与句C(8.2s) 都跨镜 → 各返回一条。"""
        a, c = "/audio/a.mp3", "/audio/c.mp3"
        segs = [
            _seg(1, 0.0, 5.34, [_line("女生", "句A", "head", 0.0, 3.0, a)],
                 [{"role_name": "女生", "visibility": "visible"}]),
            _seg(2, 5.34, 6.34, [_line("女生", "句A", "tail", 0.0, 1.9, a)],
                 [{"role_name": "女生", "visibility": "visible"}]),
            _seg(3, 8.2, 14.74, [_line("女生", "句C", "head", 0.0, 2.0, c)],
                 [{"role_name": "女生", "visibility": "visible"}]),
            _seg(4, 14.74, 15.74, [_line("女生", "句C", "tail", 0.0, 1.0, c)],
                 [{"role_name": "女生", "visibility": "visible"}]),
        ]
        vd = {("女生", "威严", get_md5("句A")): 5.04, ("女生", "威严", get_md5("句C")): 6.24}
        sents = find_multi_shot_sentences(segs, vd)
        assert len(sents) == 2
        starts = sorted(s["merged_start"] for s in sents)
        assert starts == [0.0, 8.2]
