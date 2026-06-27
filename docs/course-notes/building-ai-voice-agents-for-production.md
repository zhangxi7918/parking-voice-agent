# Building AI Voice Agents for Production 课程笔记

来源：

- B 站视频：[构建生产级AI语音助手 | Building AI Voice Agents for Production](https://www.bilibili.com/video/BV1A25LzMEkQ)
- 官方课程：[DeepLearning.AI short course](https://www.deeplearning.ai/short-courses/building-ai-voice-agents-for-production)

课程主线：生产级语音 Agent 不是“LLM 加语音输入输出”这么简单。真正影响体验的是实时音频传输、VAD、turn detection、STT、LLM、TTS、上下文同步、中断处理和端到端延迟控制。

## 1. Introduction

课程以 Andrew Ng 团队和 RealAvatar 构建会话式头像的项目为例：

- 输入侧：用 STT 将用户语音转成文本。
- 推理侧：用 agentic workflow / LLM 生成回复。
- 输出侧：用 TTS 将文本合成为语音，示例中使用 ElevenLabs 生成类似 Andrew 的声音。
- 生产化侧：为了支持大量并发用户，需要云基础设施、实时网络传输和音频集成能力。
- 通信侧：引入 LiveKit 作为实时通信基础设施，承载前端用户和后端 Agent 之间的低延迟音频流。

课程强调两个目标：

- 让语音 Agent 有“存在感”，像一个正在对话的人，而不是一次性问答接口。
- 让语音链路足够快，用户能自然打断、追问、纠正，而不是等待完整录音上传和完整音频下载。

## 2. Voice Agent Overview

### 两类架构

语音 Agent 常见有两种实现路线：

- Speech-to-speech / realtime API：
  - 直接输入语音、输出语音。
  - 实现简单，语音自然度可能更好。
  - 缺点是中间过程较黑盒，可控性、可观测性、组件替换能力较弱。
- Pipeline / cascaded architecture：
  - 典型链路是 `VAD -> STT -> LLM/Agent -> TTS`。
  - 工程复杂度更高。
  - 优点是每一层都可替换、可观测、可优化，更适合生产环境做质量、成本、延迟取舍。

### 核心组件

- VAD：判断音频里是否有人声，减少无效音频进入 STT，也降低空白音频导致的幻觉和成本。
- End-of-turn detection：判断用户这一轮是否说完。难点在于用户可能只是停顿、思考、换气，而不是真的结束。
- STT / ASR：将语音转成文本。专业领域中，领域词汇识别非常关键。
- LLM / Agentic workflow：负责推理、工具调用、记忆、规划和生成回复。
- TTS：将回复文本合成为自然语音。这里会涉及音色、口音、专有名词发音、首字节延迟等问题。

### 延迟基线

课程给出的关键直觉：

- 人类对话中，人们通常期待对方在非常短的窗口内接话。
- 如果语音 Agent 的响应超过 1 秒多，用户会明显感觉“不自然”。
- Pipeline 中每一层都会引入延迟。即使单层看起来不慢，累加后也会破坏会话感。

优化方向：

- 实时流式处理，避免等完整音频、完整文本、完整语音都生成完。
- 用低延迟网络和协议传输音频。
- 重点关注 LLM 的 time to first token 和 TTS 的 time to first byte。

## 3. End-to-End Architecture Part 1

### 为什么 HTTP / WebSocket 不理想

语音 Agent 的本质是实时传输音频包。不同协议的取舍会直接影响体验。

- TCP 重可靠性，弱实时性：
  - TCP 会保证顺序和重传。
  - 一旦中间某个包丢失或延迟，后续包即使已经到了也要等它，这就是 head-of-line blocking。
  - 对语音来说，这会造成卡顿和冻结。
- UDP 重实时性，允许应用自己处理缺包：
  - UDP 收到什么就交给应用。
  - 应用可以选择等待、跳过、插值或从最新包继续。
  - 实时音频场景更适合这种模式。

HTTP 和 WebSocket 都建立在 TCP 之上：

- HTTP 是无状态请求响应模型，不适合长连接实时双向音频。
- WebSocket 支持持久连接和双向数据，但仍受 TCP 的顺序阻塞影响，也缺少面向音频媒体流的高级能力。

### 为什么 WebRTC 更适合语音 Agent

WebRTC 是面向实时音视频的协议栈，适合浏览器、移动端和桌面端。

优势：

- 基于 UDP，更适合低延迟媒体传输。
- 支持长连接和双向流式传输。
- 原生处理音频压缩、包时间戳、网络状况评估和发送节奏控制。
- 对中断处理有帮助，因为每个包带时间信息，可以知道用户听到了哪里。

挑战：

- WebRTC 本身复杂，连接建立和媒体协商成本高。
- 标准 WebRTC 偏 peer-to-peer，跨地域传输时会受到公网路径和拥塞影响。
- 要全球低延迟，需要在多个区域部署基础设施或使用现成媒体网络。

### LiveKit 的角色

课程把 LiveKit 定位为 WebRTC 复杂度和全球媒体网络的抽象层：

- 客户端 SDK 负责建立用户端和 Agent 之间的持久连接。
- Agent SDK 负责 Agent 运行、房间连接、会话上下文和音频管线。
- LiveKit Cloud 通过全球分布式媒体服务器优化用户与 Agent 之间的网络路径。

一个关键数字：课程提到 LiveKit Cloud 的网络路径优化在实践中可降低约 20% 到 50% 的用户到 Agent 网络延迟。

## 4. End-to-End Architecture Part 2

### Agent 是有状态程序

语音 Agent 不是一次函数调用，而是一个有状态程序：

- 消费来自用户设备的实时音频流。
- 将语音转为文本并维护会话上下文。
- 调用 LLM、工具、数据库、RAG 或外部服务。
- 生成文本，再将文本转成音频流回用户。
- 为每个用户或每个房间启动一个 Agent 实例。

### Pipeline 执行过程

典型生产链路：

1. 用户音频通过 WebRTC 持续流入 Agent。
2. Agent 将音频转发给 STT，STT 流式返回转写片段。
3. Turn detection 判断用户是否说完。
4. 用户说完后，Agent 将完整 turn 的文本和上下文发送给 LLM。
5. LLM token 流式输出。
6. Agent 按句子或合适片段将 LLM 输出发送给 TTS。
7. TTS 流式生成音频。
8. Agent 将音频字节通过 WebRTC 返回客户端播放。

重点不是“串行执行完每一步”，而是尽可能让 STT、LLM、TTS 都流式工作，让后续阶段尽早开始。

### Turn detection

Turn detection 是语音 Agent 像不像人的关键之一。它通常组合两类信号：

- 信号层：VAD 判断当前有没有人声。
- 语义层：语义 turn detector 根据转写文本和最近几轮上下文判断用户是否真的说完。

仅靠静音不够，因为用户可能在句中停顿。语义模型可以识别“这句话还没说完”，从而延迟触发 end-of-turn。

### 中断处理

当用户在 Agent 说话时插话，系统需要：

- 用 VAD 检测到用户新的人声输入。
- 停止下游正在进行的 LLM 推理或 TTS 合成。
- 清空尚未播放或尚未发送的 Agent 音频。
- 根据时间戳同步上下文，只保留用户实际听到的 Agent 回复内容。

这一点对生产级体验很重要。否则 Agent 会继续说完旧回复，或者上下文里包含用户从未听到的内容。

## 5. Voice Agent Components

Pipeline 架构的最大价值是每层可以针对业务目标独立取舍：

- 医疗分诊：STT 准确率更重要，要优先识别专业术语。
- 餐厅订位：LLM 推理和工具调用可靠性更重要，要避免重复订位或错误时间。
- 高频客服：成本和延迟可能比音色定制更重要。
- 品牌型虚拟人：TTS 音色、自然度和发音控制更重要。

各层设计要点：

- VAD：
  - 减少发送给 STT 的无效音频。
  - 降低空白音频触发错误转写或幻觉的概率。
  - 降低 STT 成本。
- STT：
  - 选择语言覆盖范围。
  - 考虑是否需要直接语音翻译。
  - 电话场景可选针对 telephony 训练或优化过的模型。
- LLM：
  - 处理推理、工具调用、内容过滤和业务约束。
  - 往往是最大延迟来源。
  - 模型能力、速度和成本要按业务场景调优。
- TTS：
  - 选择声音、口音、语速和风格。
  - 支持专有名词或业务词发音覆盖。
  - 首字节延迟决定用户多久听到 Agent 开始说话。

课程实践中用 LiveKit Agent 类定义 assistant，用 session 组合 STT、LLM、TTS、VAD 插件，通过 room 将用户和 Agent 连接起来。

### 代码演示：最小可运行 Agent

这一节的代码演示目标不是搭一个完整业务系统，而是证明一个基础语音 Agent 可以跑起来，并能替换 TTS 声音。

演示结构：

1. 导入 LiveKit Agent 相关类和插件。
2. 导入 STT、LLM、TTS、VAD 所需 provider。
3. 读取环境变量和配置日志。
4. 定义一个继承 `Agent` 的 assistant 类。
5. 在 `entrypoint` 中连接 LiveKit room。
6. 创建 `AgentSession`，把 STT、LLM、TTS、VAD 组合成一条 pipeline。
7. 把 assistant 交给 session，注册成可被 LiveKit dispatch 的 worker。
8. 运行后用 LiveKit playground 与 Agent 对话。

按课程旁白可确认的代码骨架如下。原 notebook 需要登录课程 workspace 才能查看，下面是结构化复原，不是逐字源码：

```python
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession
from livekit.plugins import elevenlabs, openai, silero

load_dotenv()


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are a helpful voice assistant."
        )


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=openai.STT(),
        llm=openai.LLM(model="gpt-4o"),
        tts=elevenlabs.TTS(
            voice_id="custom_or_provider_voice_id",
        ),
    )

    await session.start(
        room=ctx.room,
        agent=Assistant(),
    )


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(entrypoint_fnc=entrypoint)
    )
```

这个 demo 里有几个生产化含义：

- `Agent` 保存 instructions、会话消息、当前轮次、是否允许被打断、可用工具等状态。
- `AgentSession` 是 pipeline 的装配点，决定 STT、LLM、TTS、VAD 由哪些 provider 承担。
- `room` 是用户和 Agent 对话的连接原语。每个新房间可以触发一个 Agent 实例。
- 替换声音只需要改 TTS 配置，例如设置 ElevenLabs 的 `voice_id`。
- 代码运行后，课程用 LiveKit playground 做前端测试，避免一开始就投入 UI 开发。

## 6. Optimizing Latency

### 端到端延迟拆解

语音 Agent 延迟不应该只看总耗时，要拆成可定位的指标：

- VAD start delay：确认用户开始说话可能损失约 15 到 20 ms。
- End-of-turn delay：判断用户说完的时间。
- STT latency：音频片段转写耗时，以及是否支持流式转写。
- LLM time to first token：模型产出第一个 token 的时间。
- LLM tokens per second：后续 token 的生成速度。
- TTS time to first byte：TTS 产出第一段音频字节的时间。
- TTS render time：完整音频生成耗时。

课程强调：

- LLM 阶段最该关注 time to first token。
- TTS 阶段最该关注 time to first byte。
- 总渲染时间不是唯一重点，只要后续音频生成速度快于播放速度，就不会卡顿。

### 流式优化策略

- STT 不等用户整段说完，而是在说话过程中持续转写片段。
- Turn detection 只决定什么时候把完整 turn 交给 LLM，不阻塞 STT 流式转写。
- LLM 不等完整回复生成完，而是 token 流式输出。
- TTS 不等完整回复文本，而是尽早消费 LLM 输出片段并流式合成音频。

### 模型选择的影响

课程示例中，通过把 LLM 从 GPT-4o 换成 GPT-4o-mini，time to first token 明显下降，响应体感接近提升一倍。

工程启发：

- 不要只用“最强模型”作为默认选择。
- 对语音交互来说，稍弱但快很多的模型可能带来更好的整体体验。
- 可以按任务拆分模型：简单寒暄和流程推进用快模型，复杂决策或高风险步骤再升级模型。

### Metrics 代码演示

课程最后的代码演示是在上一节基础 Agent 上加 metrics collection hooks，目标是把“感觉慢”拆成具体可优化的数字。

演示新增内容：

- 导入 metrics 相关类型，用来读取 pipeline 各阶段的结构化性能数据。
- 导入 `asyncio`，让 metrics 收集和打印不阻塞主对话流程。
- 将 Agent 改名为 metrics agent，但业务逻辑基本不变。
- 对 LLM、STT、end-of-utterance、TTS 分别加 metrics wrapper / callback。
- 每当某一层产出 metrics，就在 callback 中打印到控制台。

课程中明确跟踪的指标：

| 层级 | 指标 | 含义 |
| --- | --- | --- |
| LLM | prompt tokens | 输入 token 数，影响成本和上下文膨胀 |
| LLM | completion tokens | 输出 token 数，影响 TTS 负载和回复时长 |
| LLM | tokens per second | 后续生成速度 |
| LLM | time to first token | 用户说完后，模型多久开始产出第一个 token |
| STT | audio duration | 本次转写处理的音频长度 |
| STT | streamed | 是否使用流式转写 |
| End of utterance | VAD / turn detection delay | 系统多久确认用户说话或说完 |
| End of utterance | transcription delay | turn 完成前后转写耗时 |
| TTS | time to first byte | TTS 多久产出第一段可播放音频 |
| TTS | total render time | 完整回复音频生成耗时 |
| TTS | audio duration | 生成音频自身的播放时长 |
| TTS | streamed | 是否流式合成与返回 |

结构化复原代码如下：

```python
import asyncio
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, MetricsCollectedEvent
from livekit.agents.metrics import (
    LLMMetrics,
    STTMetrics,
    EOUMetrics,
    TTSMetrics,
)
from livekit.plugins import elevenlabs, openai, silero

load_dotenv()


class MetricsAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are a helpful voice assistant."
        )


def print_llm_metrics(metrics: LLMMetrics) -> None:
    print("LLM prompt tokens:", metrics.prompt_tokens)
    print("LLM completion tokens:", metrics.completion_tokens)
    print("LLM tokens/sec:", metrics.tokens_per_second)
    print("LLM time to first token:", metrics.ttft)


def print_stt_metrics(metrics: STTMetrics) -> None:
    print("STT audio duration:", metrics.audio_duration)
    print("STT streamed:", metrics.streamed)


def print_eou_metrics(metrics: EOUMetrics) -> None:
    print("End-of-utterance delay:", metrics.end_of_utterance_delay)
    print("Transcription delay:", metrics.transcription_delay)


def print_tts_metrics(metrics: TTSMetrics) -> None:
    print("TTS time to first byte:", metrics.ttfb)
    print("TTS audio duration:", metrics.audio_duration)
    print("TTS streamed:", metrics.streamed)


async def entrypoint(ctx: agents.JobContext):
    await ctx.connect()

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=openai.STT(),
        llm=openai.LLM(model="gpt-4o"),
        tts=elevenlabs.TTS(),
    )

    @session.on("metrics_collected")
    def on_metrics_collected(ev: MetricsCollectedEvent):
        metrics = ev.metrics

        if isinstance(metrics, LLMMetrics):
            print_llm_metrics(metrics)
        elif isinstance(metrics, STTMetrics):
            print_stt_metrics(metrics)
        elif isinstance(metrics, EOUMetrics):
            print_eou_metrics(metrics)
        elif isinstance(metrics, TTSMetrics):
            print_tts_metrics(metrics)

    await session.start(
        room=ctx.room,
        agent=MetricsAgent(),
    )


if __name__ == "__main__":
    agents.cli.run_app(
        agents.WorkerOptions(entrypoint_fnc=entrypoint)
    )
```

注意：LiveKit 新版文档中，session 级 `metrics_collected` 已被标注为逐步弃用，更推荐按 provider/plugin 或每轮消息维度收集 metrics。但课程 demo 的核心思路仍然成立：把 pipeline 分层埋点，再用统一日志或 observability 系统聚合。

课程用这个 metrics demo 做了一次模型替换实验：

- 初始 LLM 使用 `gpt-4o`。
- 观察日志里的 `time to first token`，示例约为 `0.84s`。
- 将 LLM 改成 `gpt-4o-mini`。
- 再次对话后，`time to first token` 几乎快了一倍。

这里的重点不是固定选择某个模型，而是建立优化闭环：

1. 先分层采集指标。
2. 找出最大延迟来源。
3. 只替换或调整对应组件。
4. 再用同一套 metrics 验证是否真的变快。

## 对当前项目的落地启发

当前项目是停车场门岗语音代理，目标更接近生产业务流程，而不是展示型聊天。优先级建议如下：

1. 先保证 turn detection 和中断处理
   - 门岗场景中用户经常打断、补充、纠正车牌或访客信息。
   - 如果 Agent 不能及时停下，会直接影响信息采集效率。

2. 把延迟指标打进日志
   - 至少记录 STT 完成时间、LLM first token、TTS first byte、总响应首音频时间。
   - 当前项目已经有浏览器音频通道和 Qwen realtime 事件，可继续补齐端到端 metrics。
   - 日志不要只写总耗时，要按 `VAD / STT / LLM / TTS / playback` 分层。

3. 按业务选择组件，而不是追求统一最优
   - 车牌、手机号、楼栋、访客姓名的识别准确率比闲聊自然度更重要。
   - LLM 回复应短、明确、流程化，减少生成时间和误导空间。

4. 优先优化 perceived latency
   - 用户最敏感的是“我说完后多久听到回应”。
   - 回复可以分阶段：先用短句确认，再继续补充下一步。

5. 上下文同步要保守
   - 如果用户打断 Agent，只应把用户实际听到的内容写入会话上下文。
   - 否则后续抽取和企业微信摘要可能包含用户没有确认过的信息。

## 可执行检查清单

- [ ] 为每轮通话记录 `user_speech_started_at`、`end_of_turn_at`、`first_agent_audio_at`。
- [ ] 单独记录 LLM 首 token 延迟和 TTS 首字节延迟。
- [ ] 为用户打断场景增加日志：是否清空下游音频、是否停止当前推理、上下文同步到哪个时间点。
- [ ] 对门岗 Agent prompt 做短回复约束，避免长篇解释拖慢 TTS。
- [ ] 针对车牌、手机号、姓名等字段评估 STT 错误率，必要时加确认回合。
- [ ] 区分“实时 API 一体化路线”和“pipeline 组件化路线”的技术债：前者快，后者更可控。
