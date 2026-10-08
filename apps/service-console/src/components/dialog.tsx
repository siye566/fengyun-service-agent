// Accessible modal primitives; only the styles needed by the service console.
import type { ComponentProps } from 'react';
import { Dialog as Primitive } from 'radix-ui';
import { X } from 'lucide-react';

export const Dialog = Primitive.Root;
export function DialogContent({ children, className = '', ...props }: ComponentProps<typeof Primitive.Content>) {
  return <Primitive.Portal>
    <Primitive.Overlay className="service-dialog-overlay" />
    <Primitive.Content className={`service-dialog-content ${className}`} {...props}>
      {children}
      <Primitive.Close className="service-dialog-close" aria-label="关闭对话框"><X size={18} /></Primitive.Close>
    </Primitive.Content>
  </Primitive.Portal>;
}
export function DialogHeader(props: ComponentProps<'div'>) { return <div {...props} />; }
export function DialogTitle(props: ComponentProps<typeof Primitive.Title>) { return <Primitive.Title className="service-dialog-title" {...props} />; }
export function DialogDescription(props: ComponentProps<typeof Primitive.Description>) { return <Primitive.Description className="service-dialog-description" {...props} />; }
