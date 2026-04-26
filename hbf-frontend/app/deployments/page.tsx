"use client";

import { useSession } from "next-auth/react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { API_BASE_URL } from "../../lib/api";

type Deployment = {
  id: number;
  owner: string;
  repo: string;
  branch: string;
  source_dir: string;
  repository_uri: string;
  image_tag: string;
  image_uri: string;
  status: "running" | "image_pushed" | "deployed" | "error" | string;
  public_url: string | null;
  ecs_service_name: string | null;
  ecs_task_definition_arn: string | null;
  ecs_target_group_arn: string | null;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
};

function formatTimestamp(value: string | null): string {
  if (!value) return "Unknown time";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function statusClassName(status: string): string {
  if (status === "success" || status === "deployed") return "text-green-400 border-green-500/40 bg-green-500/10";
  if (status === "error") return "text-red-400 border-red-500/40 bg-red-500/10";
  return "text-yellow-300 border-yellow-500/40 bg-yellow-500/10";
}

export default function DeploymentsPage() {
  const { status } = useSession();
  const [deployments, setDeployments] = useState<Deployment[] | null>(null);

  useEffect(() => {
    if (status !== "authenticated") return;

    let cancelled = false;

    const fetchDeployments = async () => {
      const token = localStorage.getItem("token");
      if (!token) {
        if (!cancelled) {
          setDeployments([]);
        }
        return;
      }

      const res = await fetch(`${API_BASE_URL}/deployments`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (!res.ok) {
        if (!cancelled) {
          setDeployments([]);
        }
        return;
      }

      const data = (await res.json()) as Deployment[];
      if (!cancelled) {
        setDeployments(data);
      }
    };

    fetchDeployments();
    const interval = window.setInterval(fetchDeployments, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [status]);

  if (status === "loading" || (status === "authenticated" && deployments === null)) {
    return <div className="flex min-h-screen items-center justify-center text-white">Loading...</div>;
  }

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-screen items-center justify-center text-white">
        Sign in to view your deployments.
      </div>
    );
  }

  const deploymentItems = deployments ?? [];

  return (
    <div className="min-h-screen px-4 py-6 text-white md:px-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Your Deployments</h1>
          <p className="text-sm text-gray-400">
            Recent deployment attempts for the repositories you pushed through Hybrid PaaS.
          </p>
        </div>

        <Link
          href="/repos"
          className="rounded border border-gray-700 px-4 py-2 text-sm text-gray-200 transition hover:bg-white hover:text-black"
        >
          Check out ur Repos
        </Link>
      </div>

      {deploymentItems.length === 0 ? (
        <div className="rounded-xl border border-gray-800 bg-black/20 p-6 text-sm text-gray-300">
          No deployments yet. Deploy a repo first and it will show up here.
        </div>
      ) : (
        <div className="grid gap-4">
          {deploymentItems.map((deployment) => (
            <div key={deployment.id} className="rounded-xl border border-gray-800 bg-black/20 p-5">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">
                    {deployment.owner}/{deployment.repo}
                  </h2>
                  <p className="text-sm text-gray-400">
                    Branch: {deployment.branch} • Source: {deployment.source_dir}
                  </p>
                </div>

                <span
                  className={`rounded-full border px-3 py-1 text-xs uppercase tracking-wide ${statusClassName(
                    deployment.status
                  )}`}
                >
                  {deployment.status}
                </span>
              </div>

              <div className="space-y-2 text-sm text-gray-300">
                <p>Repository: {deployment.repository_uri}</p>
                <p>Image tag: {deployment.image_tag}</p>
                <p>Image URI: {deployment.image_uri}</p>
                {deployment.public_url ? (
                  <p>
                    URL:{" "}
                    <a
                      href={deployment.public_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-300 underline underline-offset-4"
                    >
                      {deployment.public_url}
                    </a>
                  </p>
                ) : null}
                {deployment.ecs_service_name ? (
                  <p>ECS service: {deployment.ecs_service_name}</p>
                ) : null}
                <p>Created: {formatTimestamp(deployment.created_at)}</p>
                <p>Updated: {formatTimestamp(deployment.updated_at)}</p>
                {deployment.error_message ? (
                  <p className="text-red-400">Error: {deployment.error_message}</p>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
