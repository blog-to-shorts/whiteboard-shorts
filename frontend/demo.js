const form = document.querySelector("#generate-form");
const urlInput = document.querySelector("#url");
const generate = document.querySelector("#generate");
const status = document.querySelector("#status");
const steps = [...document.querySelectorAll("#steps li")];
const sampleButton = document.querySelector("#show-sample");
const video = document.querySelector("#video");
const emptyPreview = document.querySelector("#empty-preview");
const videoLabel = document.querySelector("#video-label");
const download = document.querySelector("#download");
let sampleUrl;
let resultUrl;

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(typeof data?.detail === "string" ? data.detail : "서버에 연결할 수 없습니다.");
  }
  return response.json();
}

function showVideo(path, label) {
  video.src = path;
  video.hidden = false;
  emptyPreview.hidden = true;
  videoLabel.textContent = label;
  download.href = path + "?download=true";
  download.hidden = false;
}

function showSample() {
  showVideo(sampleUrl, "예시 · 건설기계기술사 독학");
  sampleButton.textContent = resultUrl ? "내 영상 보기" : "예시 보기";
}

function showProgress(job) {
  const current = Number(job.current_step);
  steps.forEach((step, index) => {
    const number = index + 1;
    step.classList.toggle("complete", job.status === "done" || number < current);
    step.classList.toggle("active", job.status === "running" && number === current);
    step.classList.toggle("failed", job.status === "error" && number === current);
    if (number === current && job.status === "running") step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });
  status.textContent = {
    queued: "요청 접수",
    running: current ? `STEP ${current} / 8` : "실행 준비 중",
    done: "완료",
    error: job.error || "영상 생성 실패",
  }[job.status];
  status.classList.toggle("error", job.status === "error");
}

sampleButton.addEventListener("click", () => {
  if (resultUrl && video.getAttribute("src") === sampleUrl) {
    showVideo(resultUrl, "내 영상 · 세로형 MP4");
    sampleButton.textContent = "예시 보기";
  } else showSample();
});

request("/demo/sample").then(({ video_url }) => {
  if (!video_url) return;
  sampleUrl = video_url;
  sampleButton.hidden = false;
  if (!resultUrl) showSample();
}).catch(() => {});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  generate.disabled = true;
  showProgress({ status: "queued" });
  try {
    let job = await request("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: urlInput.value.trim() }),
    });
    showProgress(job);
    while (job.status === "queued" || job.status === "running") {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      job = await request(`/jobs/${encodeURIComponent(job.job_id)}`);
      showProgress(job);
    }
    if (job.status === "done" && job.video_url) {
      resultUrl = job.video_url;
      showVideo(resultUrl, "내 영상 · 세로형 MP4");
      sampleButton.textContent = "예시 보기";
    }
  } catch (error) {
    showProgress({ status: "error", error: error.message });
  } finally {
    generate.disabled = false;
  }
});
