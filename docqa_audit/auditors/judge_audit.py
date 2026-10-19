"""生成层软判据：模型裁判出参考分，不打分不拦。

faithfulness（忠实度）：生成内容忠不忠实于原文，抓语义层面的编造。
跟硬判据（回源）互补：硬判据抓数字、编号、日期这类，软判据抓整句话忠不忠实。

要花钱（调 DeepSeek）也要 key，所以默认不跑，config 的 claims 段写
"soft_judge": true 才开。没装 deepeval 或没有 key 时，这里会跳过。

遥测：跑的时候要设 DEEPEVAL_TELEMETRY_OPT_OUT=1，别让 DeepEval 悄悄上报。
"""

from .. import model


def available():
    try:
        import deepeval  # noqa: F401
        return True
    except Exception:
        return False


def judge(answer_text, source_text):
    """返回一个 LayerResult，里面一条 INFO：忠实度分加裁判理由。"""
    layer = model.LayerResult("软判据（参考）")

    if not available():
        layer.add(model.Finding(
            "软判据", "没装 deepeval，跳过模型裁判", model.INFO,
            "参考分不是判决，没装不影响能不能交付的判断",
        ))
        return layer

    import os
    from deepeval.models import DeepSeekModel
    from deepeval.metrics import FaithfulnessMetric
    from deepeval.test_case import LLMTestCase

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        layer.add(model.Finding(
            "软判据", "没有 DEEPSEEK_API_KEY，跳过模型裁判", model.INFO,
            "参考分不是判决，没 key 不影响能不能交付的判断",
        ))
        return layer

    llm = DeepSeekModel(model="deepseek-flash", api_key=api_key)
    metric = FaithfulnessMetric(model=llm, threshold=0.5)
    tc = LLMTestCase(
        input="根据原文生成回答",
        actual_output=answer_text,
        retrieval_context=[source_text],
    )
    try:
        metric.measure(tc)
    except Exception as exc:  # 裁判挂了不影响判决，只记一笔
        layer.add(model.Finding(
            "软判据", "模型裁判跑挂了：" + str(exc), model.INFO,
            "参考分不是判决，裁判挂了不影响能不能交付的判断",
        ))
        return layer

    layer.summary["忠实度"] = round(metric.score, 3)
    layer.add(model.Finding(
        "忠实度参考分",
        f"{metric.score:.2f}｜{metric.reason}",
        model.INFO,
        "模型裁判的参考分，不打分不拦；硬判据的回源校验才是判决",
    ))
    return layer
