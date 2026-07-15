from autohawk.scoring.keyword import keyword_score


SKILLS = ["Python", "Docker", "Kubernetes", "Terraform", "AWS"]


def test_keyword_score_rewards_matches():
    score, matched = keyword_score(
        SKILLS,
        "DevOps Engineer (Kubernetes)",
        "You will use Python, Docker and Terraform on AWS.",
    )
    assert score > 50
    assert set(matched) == set(SKILLS)


def test_keyword_score_zero_for_unrelated_job():
    score, matched = keyword_score(SKILLS, "Sales Manager", "Quota-carrying B2B sales role.")
    assert score == 0 and matched == []


def test_title_match_weighs_more_than_description_match():
    in_title, _ = keyword_score(SKILLS, "Python Developer", "generic text")
    in_desc, _ = keyword_score(SKILLS, "Developer", "we use Python daily")
    assert in_title > in_desc


def test_empty_skills_scores_zero():
    assert keyword_score([], "DevOps Engineer", "Python everywhere") == (0, [])
