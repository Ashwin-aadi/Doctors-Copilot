import { Component, type ErrorInfo, type ReactNode } from "react";
import { withTranslation, type WithTranslation } from "react-i18next";
import { ErrorState } from "../components/ui/ErrorState";
import { Button } from "../components/ui/Button";

interface ErrorBoundaryProps extends WithTranslation {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

class ErrorBoundaryBase extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Route error boundary caught:", error, info.componentStack);
  }

  reset = (): void => this.setState({ error: null });

  render() {
    const { error } = this.state;
    const { t } = this.props;
    if (!error) return this.props.children;

    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <ErrorState
          title={t("errors.boundaryTitle")}
          description={t("errors.boundaryBody")}
          action={
            <Button variant="secondary" onClick={this.reset}>
              {t("errors.retry")}
            </Button>
          }
        />
      </div>
    );
  }
}

export const ErrorBoundary = withTranslation()(ErrorBoundaryBase);
