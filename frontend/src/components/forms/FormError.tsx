export interface FormErrorProps {
  message?: string | null;
  id?: string;
}

export function FormError({ message, id }: FormErrorProps) {
  if (!message) return null;
  return (
    <p id={id} role="alert" className="min-h-[1.25rem] text-xs text-critical">
      {message}
    </p>
  );
}
