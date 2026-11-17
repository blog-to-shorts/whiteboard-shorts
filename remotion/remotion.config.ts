import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// 서버(Railway)에서 렌더할 때 메모리가 순간적으로 치솟아 컨테이너가 종료되지 않도록 제한한다
// 동시에 렌더하는 크롬 탭 수와 영상 프레임 캐시(기본: 사용 가능 메모리의 절반)를 고정한다
Config.setConcurrency(2);
Config.setOffthreadVideoCacheSizeInBytes(512 * 1024 * 1024);