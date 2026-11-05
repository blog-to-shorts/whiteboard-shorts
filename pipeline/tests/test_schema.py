from pipeline.schema import Project, Scene


def test_total_duration():
    p = Project(title="t", scenes=[Scene(id=1, narration="a", image_prompt="x", duration=2.5),
                                   Scene(id=2, narration="b", image_prompt="y", duration=3.0)])
    assert p.total_duration == 5.5
