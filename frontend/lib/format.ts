export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  if (minutes >= 1440 && minutes % 1440 === 0) return `${minutes / 1440} day${minutes > 1440 ? "s" : ""}`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h} h ${m} min` : `${h} h`;
}

// Costs are stored as whole rupees.
export function formatCost(cost: number): string {
  return cost === 0 ? "Free" : `₹${cost.toLocaleString("en-IN")}`;
}

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
