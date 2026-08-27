import { Skeleton } from "../Skeleton";

export interface ListSkeletonProps {
  rows?: number;
}

export function ListSkeleton({ rows = 5 }: ListSkeletonProps) {
  return (
    <div className="flex flex-col gap-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
