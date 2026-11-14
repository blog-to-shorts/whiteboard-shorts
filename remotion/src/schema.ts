import { z } from "zod";
import { zColor } from "@remotion/zod-types";
import { DEFAULT_SUBTITLE_BOTTOM, MAX_SUBTITLE_BOTTOM } from "./layout";

// Remotion Studio 오른쪽 "Props" 패널에서 자막·제목 모양을 바로 바꿔 볼 수 있게 하는 스키마.
// 실제 렌더 값은 .env(SUBTITLE_*, TITLE_*) → s08_render.py가 넘긴다.
const cue = z.object({ start: z.number(), end: z.number(), text: z.string() });
const scene = z.object({
    id: z.number(),
    narration: z.string(),
    video: z.string(),
    duration: z.number(),
    cues: z.array(cue),
    artworkBounds: z.object({ left: z.number(), top: z.number(), right: z.number(), bottom: z.number() }).optional(),
    numericHighlight: z.object({ value: z.string(), start: z.number() }).optional(),
});

export const videoSchema = z.object({
    title: z.string(),
    fps: z.number(),
    scenes: z.array(scene),
    introLogo: z.string().optional(),
    style: z
        .object({
            subtitle: z.object({
                font: z.string(),
                size: z.number().min(36).max(96),
                weight: z.number().min(100).max(900).step(100),
                color: zColor(),
                bottom: z.number().min(DEFAULT_SUBTITLE_BOTTOM).max(MAX_SUBTITLE_BOTTOM),
                google: z.string(),
                url: z.string(),
            }).partial(),
            title: z.object({
                font: z.string(),
                size: z.number().min(48).max(140),
                color: zColor(),
                google: z.string(),
                url: z.string(),
            }).partial(),
        })
        .partial()
        .optional(),
});
