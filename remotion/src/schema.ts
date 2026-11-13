import { z } from "zod";
import { zColor } from "@remotion/zod-types";

// Remotion Studio 오른쪽 "Props" 패널에서 자막·제목 모양을 바로 바꿔 볼 수 있게 하는 스키마.
// 실제 렌더 값은 .env(SUBTITLE_*, TITLE_*) → s08_render.py가 넘긴다.
const cue = z.object({ start: z.number(), end: z.number(), text: z.string() });
const scene = z.object({
    id: z.number(),
    narration: z.string(),
    video: z.string(),
    duration: z.number(),
    cues: z.array(cue),
});

export const videoSchema = z.object({
    title: z.string(),
    fps: z.number(),
    scenes: z.array(scene),
    style: z
        .object({
            subtitle: z.object({
                font: z.string(),
                size: z.number().min(24).max(120),
                weight: z.number().min(100).max(900).step(100),
                color: zColor(),
                bottom: z.number().min(0).max(900),
                google: z.string(),
                url: z.string(),
            }).partial(),
            title: z.object({
                font: z.string(),
                size: z.number().min(30).max(160),
                color: zColor(),
                top: z.number().min(0).max(600),
                google: z.string(),
                url: z.string(),
            }).partial(),
        })
        .partial()
        .optional(),
});
