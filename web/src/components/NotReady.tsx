import { Link } from "react-router";
import { DatabaseIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { isNotSynced, errorMessage } from "@/lib/api";

/** Friendly state for 404 "league data isn't synced yet"; generic error otherwise. */
export function NotReady({ error }: { error: unknown }) {
  if (isNotSynced(error)) {
    return (
      <Alert className="mx-auto max-w-lg">
        <DatabaseIcon />
        <AlertTitle>League data not synced yet</AlertTitle>
        <AlertDescription>
          <p>Sync your ESPN league first, then come back to this screen.</p>
          <Button asChild size="sm" className="mt-2 w-fit">
            <Link to="/">Go to Dashboard</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert variant="destructive" className="mx-auto max-w-lg">
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription>{errorMessage(error)}</AlertDescription>
    </Alert>
  );
}
