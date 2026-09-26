"""AI-assisted discovery: the decorator, the mode gating, and the reply validator.

The model's reply is untrusted input, so most of this file is about what happens
when it lies: invented paths, traversal attempts, a `kind` that contradicts the
extension, a made-up language, or no JSON at all. In every case the import must
still go through on the filename heuristic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.domain.errors import AiError
from src.domain.media import ExternalTrack, MediaInfo, Track
from src.domain.naming import EpisodeRef
from src.infrastructure.ai.discovery import AiAssistedTrackDiscovery, materialise
from src.infrastructure.ai.prompt import MAX_DESCRIBED, build
from src.infrastructure.filesystem.track_discovery import FilesystemTrackDiscovery
from tests.conftest import touch
from tests.stubs import StubProber


class StubCompleter:
    """Records what it was asked, replies with whatever it was primed with."""

    def __init__(self, reply: str | Exception = '{"tracks": []}') -> None:
        self._reply = reply
        self.calls: list[dict[str, Any]] = []

    def complete(self, *, system: str, user: str, timeout: float) -> str:
        self.calls.append({"system": system, "user": user, "timeout": timeout})
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


def tracks_reply(*items: dict[str, Any]) -> str:
    return json.dumps({"tracks": list(items)})


@pytest.fixture
def release(tmp_path: Path) -> Path:
    """A layout the filename heuristic cannot attribute: opaque folder names."""
    root = tmp_path / "Some.Show.S02E05.1080p.WEB-DL"
    touch(root / "Some.Show.S02E05.1080p.WEB-DL.mkv", b"video")
    touch(root / "Zvuk 1" / "Some.Show.S02E05.track.mka", b"audio")
    touch(root / "Nadpisi" / "Some.Show.S02E05.ass", "signs")
    return root


@pytest.fixture
def video(release: Path) -> Path:
    return release / "Some.Show.S02E05.1080p.WEB-DL.mkv"


def make(
    completer: StubCompleter,
    *,
    mode: str = "fallback",
    max_entries: int = 200,
    max_tracks: int = 24,
    name_tracks: bool = False,
) -> AiAssistedTrackDiscovery:
    return AiAssistedTrackDiscovery(
        heuristic=FilesystemTrackDiscovery(),
        completer=completer,
        mode=mode,  # type: ignore[arg-type]
        max_entries=max_entries,
        max_tracks=max_tracks,
        name_tracks=name_tracks,
    )


class TestModeGating:
    def test_off_never_calls_the_model(self, video: Path) -> None:
        completer = StubCompleter()

        found = make(completer, mode="off").discover(video)

        assert completer.calls == []
        assert found == FilesystemTrackDiscovery().discover(video)

    def test_fallback_calls_the_model_when_the_heuristic_finds_nothing(
        self, tmp_path: Path
    ) -> None:
        # Unmarked sidecars beside several videos: the heuristic refuses to guess.
        root = tmp_path / "Show.S01.Pack"
        video_path = touch(root / "Show.S01E01.mkv", b"video")
        touch(root / "Show.S01E02.mkv", b"video")
        touch(root / "Subs" / "part-a.srt", "x")
        touch(root / "Subs" / "part-b.srt", "x")
        completer = StubCompleter()
        episode = EpisodeRef(season=1, episodes=(1,))

        assert FilesystemTrackDiscovery().discover(video_path, episode=episode) == []

        make(completer, mode="fallback").discover(video_path, episode=episode)

        assert len(completer.calls) == 1

    def test_fallback_calls_the_model_when_a_language_is_undetermined(self, video: Path) -> None:
        completer = StubCompleter()

        found = FilesystemTrackDiscovery().discover(video)
        assert any(t.language == "und" for t in found)

        make(completer, mode="fallback").discover(video)

        assert len(completer.calls) == 1

    def test_fallback_does_not_call_the_model_when_filenames_settled_it(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "Movie.2024.1080p"
        video_path = touch(root / "Movie.2024.1080p.mkv", b"video")
        touch(root / "Movie.2024.1080p.eng.srt", "subs")
        completer = StubCompleter()

        found = make(completer, mode="fallback").discover(video_path)

        assert completer.calls == []
        assert [t.language for t in found] == ["eng"]

    def test_always_calls_the_model_even_when_the_heuristic_succeeded(self, tmp_path: Path) -> None:
        root = tmp_path / "Movie.2024.1080p"
        video_path = touch(root / "Movie.2024.1080p.mkv", b"video")
        touch(root / "Movie.2024.1080p.eng.srt", "subs")
        completer = StubCompleter(
            tracks_reply({"file": "Movie.2024.1080p.eng.srt", "language": "fre"})
        )

        found = make(completer, mode="always").discover(video_path)

        assert len(completer.calls) == 1
        assert [t.language for t in found] == ["fre"]
        assert [t.source for t in found] == ["ai"]

    def test_verify_consults_the_model_but_keeps_the_heuristic_answer(self, tmp_path: Path) -> None:
        root = tmp_path / "Movie.2024.1080p"
        video_path = touch(root / "Movie.2024.1080p.mkv", b"video")
        touch(root / "Movie.2024.1080p.eng.srt", "subs")
        completer = StubCompleter(
            tracks_reply({"file": "Movie.2024.1080p.eng.srt", "language": "fre"})
        )

        found = make(completer, mode="verify").discover(video_path)

        assert len(completer.calls) == 1
        assert [t.language for t in found] == ["eng"]
        assert [t.source for t in found] == ["heuristic"]


class TestNameTracks:
    """The provider writes the labels; the filenames keep choosing the files."""

    @pytest.fixture
    def settled(self, tmp_path: Path) -> Path:
        root = tmp_path / "Movie.2024.1080p"
        video_path = touch(root / "Movie.2024.1080p.mkv", b"video")
        touch(root / "Movie.2024.1080p.eng.srt", "subs")
        touch(root / "Movie.2024.1080p.rus.mka", b"audio")
        return video_path

    def test_the_provider_is_consulted_even_when_the_filenames_settled_it(
        self, settled: Path
    ) -> None:
        completer = StubCompleter()

        make(completer, mode="fallback", name_tracks=True).discover(settled)

        assert len(completer.calls) == 1

    def test_the_provider_title_becomes_the_track_name(self, settled: Path) -> None:
        completer = StubCompleter(
            tracks_reply(
                {"file": "Movie.2024.1080p.rus.mka", "language": "rus", "title": "Russian (Kubik)"}
            )
        )

        found = make(completer, mode="fallback", name_tracks=True).discover(settled)

        by_name = {t.path.name: t for t in found}
        assert by_name["Movie.2024.1080p.rus.mka"].name == "Russian (Kubik)"
        # Untouched by the reply, so it keeps the name the filename produced.
        assert by_name["Movie.2024.1080p.eng.srt"].name == "English"

    def test_naming_does_not_let_the_provider_change_the_selection(self, settled: Path) -> None:
        completer = StubCompleter(
            tracks_reply({"file": "Movie.2024.1080p.eng.srt", "language": "fre", "title": "French"})
        )

        found = make(completer, mode="fallback", name_tracks=True).discover(settled)

        assert len(found) == 2
        subtitle = next(t for t in found if t.path.suffix == ".srt")
        assert subtitle.language == "eng"
        assert subtitle.name == "French"
        assert all(t.source == "heuristic" for t in found)

    def test_a_provider_failure_leaves_the_names_alone(self, settled: Path) -> None:
        completer = StubCompleter(AiError("connection refused"))

        found = make(completer, mode="fallback", name_tracks=True).discover(settled)

        assert sorted(t.name or "" for t in found) == ["English", "Russian"]

    def test_verify_stays_a_shadow_mode(self, settled: Path) -> None:
        completer = StubCompleter(
            tracks_reply(
                {"file": "Movie.2024.1080p.eng.srt", "language": "eng", "title": "English (AI)"}
            )
        )

        found = make(completer, mode="verify", name_tracks=True).discover(settled)

        assert all(t.name != "English (AI)" for t in found)

    def test_an_undetermined_release_still_hands_selection_to_the_provider(
        self, video: Path
    ) -> None:
        completer = StubCompleter(
            tracks_reply({"file": "Nadpisi/Some.Show.S02E05.ass", "language": "rus"})
        )

        found = make(completer, mode="fallback", name_tracks=True).discover(video)

        assert [t.source for t in found] == ["ai"]


class TestDegradation:
    def test_a_provider_failure_keeps_the_heuristic_result(self, video: Path) -> None:
        completer = StubCompleter(AiError("connection refused"))

        found = make(completer).discover(video)

        assert [t.path.name for t in found] == sorted(t.path.name for t in found)
        assert len(found) == 2
        assert all(t.source == "heuristic" for t in found)

    def test_an_unexpected_exception_is_swallowed(self, video: Path) -> None:
        completer = StubCompleter(RuntimeError("client blew up"))

        assert len(make(completer).discover(video)) == 2

    def test_a_non_json_reply_keeps_the_heuristic_result(self, video: Path) -> None:
        completer = StubCompleter("I'm sorry, I can't help with that.")

        found = make(completer).discover(video)

        assert all(t.source == "heuristic" for t in found)

    def test_an_empty_ai_answer_keeps_the_heuristic_result(self, video: Path) -> None:
        completer = StubCompleter('{"tracks": []}')

        found = make(completer).discover(video)

        assert len(found) == 2
        assert all(t.source == "heuristic" for t in found)

    def test_too_many_candidates_skips_the_call_entirely(self, tmp_path: Path) -> None:
        root = tmp_path / "Huge.Pack"
        video_path = touch(root / "Huge.Pack.S01E01.mkv", b"video")
        for index in range(12):
            touch(root / "Subs" / f"{index}_something.srt", "x")
        completer = StubCompleter()

        make(completer, max_entries=5).discover(
            video_path, episode=EpisodeRef(season=1, episodes=(1,))
        )

        assert completer.calls == []

    def test_a_folder_with_no_sidecars_skips_the_call(self, tmp_path: Path) -> None:
        root = tmp_path / "Bare"
        video_path = touch(root / "Bare.mkv", b"video")
        completer = StubCompleter()

        assert make(completer).discover(video_path) == []
        assert completer.calls == []


class TestReplyValidation:
    def index(self, release: Path) -> dict[str, Path]:
        built = build(release / "Some.Show.S02E05.1080p.WEB-DL.mkv")
        assert built is not None
        return built.index

    def test_accepts_a_well_formed_proposal(self, release: Path) -> None:
        reply = tracks_reply(
            {
                "file": "Zvuk 1/Some.Show.S02E05.track.mka",
                "kind": "audio",
                "language": "rus",
                "title": "Russian (Studio One)",
                "forced": False,
                "hearing_impaired": False,
                "variant": "Studio One",
            }
        )

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert len(tracks) == 1
        track = tracks[0]
        assert track.path == release / "Zvuk 1" / "Some.Show.S02E05.track.mka"
        assert track.kind == "audio"
        assert track.language == "rus"
        assert track.name == "Russian (Studio One)"
        assert track.variant == "Studio One"
        assert track.source == "ai"

    @pytest.mark.parametrize(
        "proposed",
        [
            "../../../../etc/passwd",
            "/etc/passwd",
            "Zvuk 1/../../../secrets.srt",
            "./Zvuk 1/Some.Show.S02E05.track.mka",
            "Zvuk 2/Some.Show.S02E05.track.mka",
            "Some.Show.S02E05.invented.srt",
        ],
    )
    def test_rejects_any_path_that_is_not_a_listed_candidate(
        self, release: Path, proposed: str
    ) -> None:
        reply = tracks_reply({"file": proposed, "language": "eng"})

        assert materialise(reply, index=self.index(release), max_tracks=24) == []

    def test_a_traversal_attempt_never_reaches_the_filesystem(
        self, release: Path, tmp_path: Path
    ) -> None:
        outside = touch(tmp_path / "outside.srt", "secret")
        reply = tracks_reply({"file": f"../{outside.name}", "language": "eng"})

        assert materialise(reply, index=self.index(release), max_tracks=24) == []

    def test_the_kind_comes_from_the_extension_not_the_model(self, release: Path) -> None:
        reply = tracks_reply(
            {"file": "Nadpisi/Some.Show.S02E05.ass", "kind": "audio", "language": "rus"}
        )

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert [t.kind for t in tracks] == ["subtitles"]

    @pytest.mark.parametrize("raw", ["Klingon", "xx", "", None, 7, {"code": "eng"}])
    def test_an_unrecognised_language_becomes_und(self, release: Path, raw: Any) -> None:
        reply = tracks_reply({"file": "Nadpisi/Some.Show.S02E05.ass", "language": raw})

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert [t.language for t in tracks] == ["und"]

    def test_a_language_name_is_normalised_to_iso_639_2(self, release: Path) -> None:
        reply = tracks_reply({"file": "Nadpisi/Some.Show.S02E05.ass", "language": "Russian"})

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert [t.language for t in tracks] == ["rus"]

    @pytest.mark.parametrize("raw", ["true", 1, None, "yes"])
    def test_only_a_real_boolean_sets_a_flag(self, release: Path, raw: Any) -> None:
        reply = tracks_reply(
            {"file": "Nadpisi/Some.Show.S02E05.ass", "forced": raw, "hearing_impaired": raw}
        )

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert tracks[0].forced is False
        assert tracks[0].hearing_impaired is False

    def test_labels_are_stripped_of_control_characters_and_capped(self, release: Path) -> None:
        reply = tracks_reply(
            {
                "file": "Nadpisi/Some.Show.S02E05.ass",
                "title": "Signs\n\x00--track-order\r  evil " + "x" * 400,
                "variant": "   ",
            }
        )

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert "\n" not in (tracks[0].name or "")
        assert "\x00" not in (tracks[0].name or "")
        assert len(tracks[0].name or "") <= 120
        assert tracks[0].variant is None

    def test_a_missing_title_falls_back_to_the_derived_one(self, release: Path) -> None:
        reply = tracks_reply(
            {
                "file": "Nadpisi/Some.Show.S02E05.ass",
                "language": "rus",
                "title": None,
                "forced": True,
            }
        )

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert tracks[0].name == "Russian (Forced)"

    def test_duplicate_proposals_collapse_to_one_track(self, release: Path) -> None:
        reply = tracks_reply(
            {"file": "Nadpisi/Some.Show.S02E05.ass", "language": "rus"},
            {"file": "Nadpisi/Some.Show.S02E05.ass", "language": "eng"},
        )

        tracks = materialise(reply, index=self.index(release), max_tracks=24)

        assert [t.language for t in tracks] == ["rus"]

    def test_the_track_list_is_capped(self, release: Path) -> None:
        reply = tracks_reply(
            {"file": "Nadpisi/Some.Show.S02E05.ass"},
            {"file": "Zvuk 1/Some.Show.S02E05.track.mka"},
        )

        assert len(materialise(reply, index=self.index(release), max_tracks=1)) == 1

    def test_a_bare_json_array_is_accepted(self, release: Path) -> None:
        reply = json.dumps([{"file": "Nadpisi/Some.Show.S02E05.ass", "language": "rus"}])

        assert len(materialise(reply, index=self.index(release), max_tracks=24)) == 1

    def test_a_fenced_code_block_is_accepted(self, release: Path) -> None:
        reply = (
            "```json\n"
            + tracks_reply({"file": "Nadpisi/Some.Show.S02E05.ass", "language": "rus"})
            + "\n```"
        )

        assert len(materialise(reply, index=self.index(release), max_tracks=24)) == 1

    @pytest.mark.parametrize(
        "reply",
        ["not json", "", "null", '{"tracks": "everything"}', '{"other": []}', "[1, 2, 3]"],
    )
    def test_unusable_replies_yield_no_tracks(self, release: Path, reply: str) -> None:
        assert materialise(reply, index=self.index(release), max_tracks=24) == []


class TestPrompt:
    def test_sends_only_relative_names(self, video: Path, release: Path) -> None:
        built = build(video)

        assert built is not None
        assert str(release) not in built.user
        assert str(release.parent) not in built.user
        assert "Zvuk 1/Some.Show.S02E05.track.mka" in built.user

    def test_names_the_target_video_and_its_siblings(self, tmp_path: Path) -> None:
        root = tmp_path / "Pack"
        video_path = touch(root / "Pack.S01E01.mkv", b"video")
        touch(root / "Pack.S01E02.mkv", b"video")
        touch(root / "Subs" / "Pack.S01E01.eng.srt", "x")

        built = build(video_path)

        assert built is not None
        payload = json.loads(built.user)
        assert payload["video"] == "Pack.S01E01.mkv"
        assert payload["other_videos_in_folder"] == ["Pack.S01E02.mkv"]

    def test_passes_the_episode_marker_through(self, video: Path) -> None:
        built = build(video, episode=EpisodeRef(season=2, episodes=(5,)))

        assert built is not None
        assert json.loads(built.user)["episode"] == {"season": 2, "episodes": [5]}

    def test_videos_are_not_offered_as_candidates(self, video: Path) -> None:
        built = build(video)

        assert built is not None
        assert all(not f.endswith(".mkv") for f in built.index)

    def test_describes_a_sidecar_by_its_own_tags(self, video: Path, release: Path) -> None:
        audio = release / "Zvuk 1" / "Some.Show.S02E05.track.mka"
        declared = Track(index=1, kind="audio", codec_id="A_AC3", language="rus", name="Kubik")
        prober = StubProber(
            infos={audio: MediaInfo(path=audio, container="Matroska", tracks=(declared,))}
        )

        built = build(video, prober=prober)

        assert built is not None
        entry = _candidate(built.user, "Zvuk 1/Some.Show.S02E05.track.mka")
        assert entry["tags"] == {"language": "rus", "title": "Kubik"}
        assert built.tagged == {"Zvuk 1/Some.Show.S02E05.track.mka": "rus"}

    def test_sends_an_excerpt_of_a_text_subtitle(self, tmp_path: Path) -> None:
        root = tmp_path / "Cold"
        video_path = touch(root / "09. Cold.avi", b"video")
        cue = "1\n00:00:01,000 --> 00:00:02,000\nПривет, как дела?\n"  # noqa: RUF001
        touch(root / "09. Cold.srt", cue)

        built = build(video_path)

        assert built is not None
        assert _candidate(built.user, "09. Cold.srt")["excerpt"] == "Привет, как дела?"

    def test_only_so_many_candidates_are_described(self, tmp_path: Path) -> None:
        root = tmp_path / "Pack"
        video_path = touch(root / "Pack.S01E01.mkv", b"video")
        touch(root / "Pack.S01E02.mkv", b"video")
        cue = "1\n00:00:01,000 --> 00:00:02,000\nHello there\n"
        for n in range(MAX_DESCRIBED + 5):
            touch(root / "Subs" / f"Pack.S01E02.{n:02}.srt", cue)
        touch(root / "Subs" / "Pack.S01E01.zz.srt", cue)

        built = build(video_path, episode=EpisodeRef(season=1, episodes=(1,)))

        assert built is not None
        candidates = json.loads(built.user)["candidates"]
        assert sum(1 for c in candidates if "excerpt" in c) == MAX_DESCRIBED
        assert "excerpt" in _candidate(built.user, "Subs/Pack.S01E01.zz.srt")


def _candidate(user: str, file: str) -> dict[str, Any]:
    return next(c for c in json.loads(user)["candidates"] if c["file"] == file)


class TestDeclaredLanguage:
    def test_a_model_shrug_keeps_the_declared_language(self, release: Path) -> None:
        built = build(release / "Some.Show.S02E05.1080p.WEB-DL.mkv")
        assert built is not None
        reply = tracks_reply({"file": "Zvuk 1/Some.Show.S02E05.track.mka", "language": "und"})

        [track] = materialise(
            reply,
            index=built.index,
            max_tracks=24,
            tagged={"Zvuk 1/Some.Show.S02E05.track.mka": "rus"},
        )

        assert (track.language, track.name) == ("rus", "Russian")

    def test_the_model_may_still_overrule_a_tag(self, release: Path) -> None:
        built = build(release / "Some.Show.S02E05.1080p.WEB-DL.mkv")
        assert built is not None
        reply = tracks_reply({"file": "Zvuk 1/Some.Show.S02E05.track.mka", "language": "eng"})

        [track] = materialise(
            reply,
            index=built.index,
            max_tracks=24,
            tagged={"Zvuk 1/Some.Show.S02E05.track.mka": "rus"},
        )

        assert track.language == "eng"


def test_ai_discovery_does_not_modify_the_source_folder(release: Path, video: Path) -> None:
    completer = StubCompleter(
        tracks_reply({"file": "Zvuk 1/Some.Show.S02E05.track.mka", "language": "rus"})
    )
    before = _snapshot(release)

    make(completer, mode="always").discover(video)

    assert _snapshot(release) == before


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_a_stub_completer_satisfies_the_protocol() -> None:
    from src.application.interfaces.ai import ChatCompleter

    completer: ChatCompleter = StubCompleter()

    assert completer.complete(system="s", user="u", timeout=1.0) == '{"tracks": []}'


def test_the_decorator_satisfies_the_track_discovery_protocol() -> None:
    from src.application.interfaces.track_source import TrackDiscovery

    discovery: TrackDiscovery = make(StubCompleter())
    tracks: list[ExternalTrack] = discovery.discover(Path("/nonexistent/video.mkv"))

    assert tracks == []
