import { Link } from "react-router-dom";
import { EmptyState } from "../components/common/Feedback";
export default function NotFoundPage() {
  return (
    <EmptyState title="No such page">
      <p>
        <Link to="/">Go back and upload a Balance Sheet</Link>
      </p>
    </EmptyState>
  );
}
