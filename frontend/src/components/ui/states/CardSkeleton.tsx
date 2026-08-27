import { Skeleton } from "../Skeleton";

export function CardSkeleton() {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border p-4" role="status" aria-label="Loading">
      <Skeleton className="h-5 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  );
}
