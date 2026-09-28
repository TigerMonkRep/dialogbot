"""Streaming synthesis for Chatterbox/Røst: send the first audio after a few speech tokens, not after the sentence.

Chatterbox generates speech in two stages: T3 (a 0.5B Llama) samples S3 speech tokens (25 per second of audio)
one at a time, then S3Gen (flow matching + HiFi-GAN) turns tokens into a waveform. The stock `generate()` waits
for the last token before running S3Gen, so a caller hears nothing for the whole sentence (measured 28/9 on an L4:
first audio p50 2.9 s, p95 4.0 s on the server).

Here T3 runs token by token and S3Gen decodes the tokens received so far every `first`/`step` tokens. Each decode
covers the whole utterance so far (the flow model attends over all of it, so earlier frames can still shift a
little); only the new tail is sent, with `holdback` samples kept back until the next decode and a short crossfade
at every seam. The flow's noise is fixed per utterance so repeated decodes agree on what was already sent.

`DecodeStitcher` (pure numpy) does the bookkeeping and is unit-tested without a model. `T3Stepper` is the token
loop: the stock loop's sampling (CFG, repetition penalty, temperature, min-p, top-p) and positional embeddings,
with a static KV cache and the one-token step replayed as a CUDA graph on GPU, where the stock loop is
bound by Python/kernel-launch overhead (~30 ms per token on an L4) rather than by the GPU.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator

import numpy as np

log = logging.getLogger("tts.streaming")

TOKEN_RATE = 25  # S3 speech tokens per second
SR = 24000
SAMPLES_PER_TOKEN = SR // TOKEN_RATE
LOOKAHEAD_TOKENS = 3  # the flow's encoder looks 3 tokens ahead: the audio of the newest 3 tokens is provisional


class DecodeStitcher:
    """Turns successive full-utterance decodes into a gap-free stream of new samples.

    feed(wav, final) is called with the full waveform decoded so far and returns the samples to send now.
    Everything before `emitted` has been sent. The `xfade` samples after it were sent as part of nothing yet:
    they are kept as `tail` from the previous decode and crossfaded with the new decode's version of the same
    stretch, so a seam never clicks even if the two decodes differ slightly there.
    """

    def __init__(self, holdback: int = LOOKAHEAD_TOKENS * SAMPLES_PER_TOKEN + int(0.04 * SR),
                 xfade: int = int(0.02 * SR)):
        self.holdback, self.xfade = holdback, xfade
        self.emitted = 0
        self.tail: np.ndarray | None = None
        self.done = False
        ramp = np.linspace(0.0, 1.0, xfade, dtype=np.float32)
        self.fade_in, self.fade_out = ramp, 1.0 - ramp

    def feed(self, wav: np.ndarray, final: bool = False) -> np.ndarray:
        if self.done:
            return np.zeros(0, dtype=np.float32)
        end = len(wav) if final else len(wav) - self.holdback
        if not final and end - self.emitted < 2 * self.xfade:
            return np.zeros(0, dtype=np.float32)  # not enough new audio yet
        seg = wav[self.emitted:max(end, self.emitted)].astype(np.float32, copy=True)
        if self.tail is not None:
            n = min(self.xfade, len(seg), len(self.tail))
            seg[:n] = self.tail[:n] * self.fade_out[:n] + seg[:n] * self.fade_in[:n]
        if final:
            self.done = True
            return seg
        self.tail = wav[end - self.xfade:end].astype(np.float32, copy=True)
        self.emitted = end - self.xfade
        return seg[:-self.xfade]


class StreamResampler:
    """Chunk-wise resampling without seams: each chunk is resampled together with the end of the previous one and
    only the new part is kept. Works in whole blocks of the rate ratio so sample positions never drift."""

    def __init__(self, sr_in: int, sr_out: int, context: int = 480):
        from math import gcd

        g = gcd(sr_in, sr_out)
        self.sr_in, self.sr_out, self.up, self.down = sr_in, sr_out, sr_out // g, sr_in // g
        self.context = (context // self.down + 1) * self.down  # whole blocks
        self.prev = np.zeros(0, dtype=np.float32)
        self.pending = np.zeros(0, dtype=np.float32)

    def _resample(self, x: np.ndarray) -> np.ndarray:
        from tts_service.engines import resample

        return resample(x, self.sr_in, self.sr_out)

    def feed(self, x: np.ndarray, final: bool = False) -> np.ndarray:
        """The filter needs samples on both sides: `context` samples before (already sent) and after (kept back
        until the next feed) each emitted stretch."""
        if self.sr_in == self.sr_out:
            return x
        buf = np.concatenate([self.pending, x]).astype(np.float32)
        usable = len(buf) if final else max(0, ((len(buf) - self.context) // self.down) * self.down)
        if not usable:
            self.pending = buf
            return np.zeros(0, dtype=np.float32)
        y = self._resample(np.concatenate([self.prev, buf]))
        skip = len(self.prev) * self.up // self.down
        out = y[skip:skip + usable * self.up // self.down] if not final else y[skip:]
        self.prev = np.concatenate([self.prev, buf[:usable]])[-self.context:]
        self.pending = buf[usable:]
        return out.astype(np.float32)


class T3Stepper:
    """Samples speech tokens one at a time (a generator), equivalent to chatterbox T3.inference."""

    def __init__(self, t3, device: str, compile_step: bool | None = None, max_cache_len: int = 2048,
                 graph: str | None = None):
        """graph: "cuda" (default on GPU) captures the one-token step once as a CUDA graph and replays it – no
        compiler needed; "compile" uses torch.compile(mode="reduce-overhead") (needs a C compiler for Triton);
        "off" keeps the static cache in eager mode. Any failure falls back to eager, never to an error."""
        self.t3, self.device, self.max_cache_len = t3, device, max_cache_len
        want = os.environ.get("TTS_T3_COMPILE", "1") != "0" if compile_step is None else compile_step
        self.static = want and str(device).startswith("cuda")
        self.graph_mode = graph or os.environ.get("TTS_T3_GRAPH", "cuda")
        self.cache = None
        self._step = None
        self._graph = None
        self.compiled = False  # a graph (captured or compiled) is in use

    def _setup_static(self):
        import torch
        from transformers import StaticCache

        self.cache = StaticCache(config=self.t3.cfg, max_cache_len=self.max_cache_len)

        def step(embeds, cache_position):
            out = self.t3.tfmr(inputs_embeds=embeds, past_key_values=self.cache, cache_position=cache_position,
                               use_cache=True)
            return out.last_hidden_state

        self._eager = self._step = step
        if self.graph_mode == "compile":
            try:
                self._step = torch.compile(step, mode="reduce-overhead", fullgraph=False)
                self.compiled = True
            except Exception:  # noqa: BLE001 - fall back to the eager static cache
                log.exception("torch.compile unavailable; eager static cache")

    def _capture(self, like):
        """Record the one-token step as a CUDA graph. Runs before a request's prefill: the warm-up writes into cache
        slot 0, and the cache is reset right after, so no request ever sees those values."""
        import torch

        try:
            self._s_emb = torch.zeros_like(like)
            self._s_pos = torch.zeros(1, dtype=torch.long, device=self.device)
            side = torch.cuda.Stream()
            side.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(side):
                for _ in range(3):
                    self._eager(self._s_emb, self._s_pos)
            torch.cuda.current_stream().wait_stream(side)
            g = torch.cuda.CUDAGraph()
            with torch.cuda.graph(g):
                self._s_out = self._eager(self._s_emb, self._s_pos)
            self._graph, self.compiled = g, True
            log.info("token step captured as a CUDA graph")
        except Exception:  # noqa: BLE001 - capture is an optimisation; eager static cache still works
            log.exception("CUDA graph capture failed; eager static cache")
            self._graph, self.compiled, self.graph_mode = None, False, "off"
            torch.cuda.synchronize()

    def _run_step(self, emb, pos):
        if self._graph is not None:
            self._s_emb.copy_(emb)
            self._s_pos.copy_(pos)
            self._graph.replay()
            return self._s_out.clone()  # the graph's output buffer is reused by the next replay
        try:
            hidden = self._step(emb, pos)
        except Exception:  # noqa: BLE001 - a failed compiled step must not take the voice down
            if not self.compiled:
                raise
            log.exception("compiled token step failed; continuing with the eager static cache")
            self.compiled, self._step = False, self._eager
            return self._eager(emb, pos)  # rewrites the same cache position, so the state stays consistent
        return hidden.clone() if self.compiled else hidden

    def tokens(self, t3_cond, text_tokens, *, temperature: float, cfg_weight: float, repetition_penalty: float,
               min_p: float, top_p: float, max_new_tokens: int = 1000) -> Iterator[int]:
        import torch
        from transformers.generation.logits_process import (
            MinPLogitsWarper,
            RepetitionPenaltyLogitsProcessor,
            TopPLogitsWarper,
        )

        t3, hp = self.t3, self.t3.hp
        text_tokens = torch.atleast_2d(text_tokens).to(dtype=torch.long, device=self.device)
        start = hp.start_speech_token * torch.ones_like(text_tokens[:, :1])
        embeds, _ = t3.prepare_input_embeds(t3_cond=t3_cond, text_tokens=text_tokens, speech_tokens=start,
                                            cfg_weight=cfg_weight)
        bos = torch.tensor([[hp.start_speech_token]], dtype=torch.long, device=self.device)
        bos_embed = t3.speech_emb(bos) + t3.speech_pos_emb.get_fixed_embedding(0)
        inputs = torch.cat([embeds, torch.cat([bos_embed, bos_embed])], dim=1)
        max_new_tokens = min(max_new_tokens, self.max_cache_len - inputs.size(1) - 1)

        if self.static:
            if self._step is None:
                self._setup_static()
            if self.graph_mode == "cuda" and self._graph is None:
                self._capture(inputs[:, :1])
            self.cache.reset()
            pos = torch.arange(inputs.size(1), device=self.device)
            hidden = t3.tfmr(inputs_embeds=inputs, past_key_values=self.cache, cache_position=pos,
                             use_cache=True).last_hidden_state
            past = None
        else:
            out = t3.tfmr(inputs_embeds=inputs, use_cache=True)
            hidden, past = out.last_hidden_state, out.past_key_values
        n_ctx = inputs.size(1)

        rep = RepetitionPenaltyLogitsProcessor(penalty=float(repetition_penalty))
        minp, topp = MinPLogitsWarper(min_p=min_p), TopPLogitsWarper(top_p=top_p)
        generated = bos.clone()
        cfg = torch.as_tensor(cfg_weight, device=self.device)
        for i in range(max_new_tokens):
            logits = t3.speech_head(hidden[:, -1, :])
            cond, uncond = logits[0:1], logits[1:2]
            logits = cond + cfg.to(cond.dtype) * (cond - uncond)
            logits = rep(generated, logits.float())
            if temperature != 1.0:
                logits = logits / temperature
            logits = topp(generated, minp(generated, logits))
            nxt = torch.multinomial(torch.softmax(logits, dim=-1), num_samples=1)
            tok = int(nxt.item())
            if tok == hp.stop_speech_token:
                return
            yield tok
            generated = torch.cat([generated, nxt], dim=1)
            emb = t3.speech_emb(nxt) + t3.speech_pos_emb.get_fixed_embedding(i + 1)
            emb = torch.cat([emb, emb])
            if self.static:
                hidden = self._run_step(emb, torch.tensor([n_ctx + i], device=self.device))
            else:
                out = t3.tfmr(inputs_embeds=emb, past_key_values=past, use_cache=True)
                hidden, past = out.last_hidden_state, out.past_key_values


def utterance_noise(model, max_tokens: int, seed: int):
    """Fixed flow noise for one utterance (80 mel bins × 2 frames per token); see decode()."""
    import torch

    g = torch.Generator(device="cpu").manual_seed(seed)
    s3 = model.s3gen
    n = max_tokens * s3.flow.token_mel_ratio
    return torch.randn(1, 80, n, generator=g).to(device=s3.device, dtype=s3.dtype)


def decode(model, tokens: list[int], noise, finalize: bool) -> np.ndarray:
    """S3Gen on the speech tokens so far → float32 waveform at 24 kHz (watermark applied by the caller).

    `noise` fixes the flow's starting noise for the utterance's own frames, so a frame gets the same noise at
    every decode and what was already sent stays consistent with what comes next. The flow is always run in its
    finalize mode (its own streaming mode mis-sizes the mask in this Chatterbox version); the newest
    LOOKAHEAD_TOKENS of an unfinished utterance are covered by the stitcher's holdback instead."""
    import torch
    from chatterbox.models.s3tokenizer import SPEECH_VOCAB_SIZE

    s3 = model.s3gen
    ids = [t for t in tokens if t < SPEECH_VOCAB_SIZE]
    if finalize and len(ids) > 1:
        ids = ids[:-1]  # the last token before EOS decodes to ~40 ms of noise (as in the stock generate)
    if not ids:
        return np.zeros(0, dtype=np.float32)
    tok = torch.tensor([ids], dtype=torch.long, device=s3.device)
    ref = {k: (v.to(device=s3.device, dtype=s3.dtype) if torch.is_tensor(v) else v)
           for k, v in model.conds.gen.items()}
    n_frames = len(ids) * s3.flow.token_mel_ratio
    mels, _ = s3.flow.inference(token=tok, token_len=torch.tensor([len(ids)], device=s3.device), finalize=True,
                                n_timesteps=10, noised_mels=noise[:, :, :n_frames], meanflow=False, **ref)
    wav, _ = s3.hift_inference(mels.to(dtype=s3.dtype), None)
    wav[:, :len(s3.trim_fade)] *= s3.trim_fade
    return wav.squeeze(0).float().cpu().numpy()
