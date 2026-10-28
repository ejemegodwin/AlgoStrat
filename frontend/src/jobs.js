import { api } from "./api";

// Application and contract responses embed only job_id. This fetches
// each referenced job once and returns { id: title } for display.
// If these lists grow, the better fix is an API-side embed.
export async function fetchJobTitles(token, jobIds) {
  const uniqueIds = [...new Set(jobIds)];
  const jobs = await Promise.all(
    uniqueIds.map((id) =>
      api(`/jobs/${id}`, { token }).catch(() => ({
        id,
        title: `Job #${id}`,
      })),
    ),
  );
  return Object.fromEntries(jobs.map((job) => [job.id, job.title]));
}
