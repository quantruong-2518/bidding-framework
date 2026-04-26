import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { UploadDropzone, MAX_FILE_BYTES } from '@/components/bids/upload-dropzone';

function makeFile(name: string, size: number, type = 'application/pdf'): File {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size, configurable: true });
  return file;
}

describe('UploadDropzone', () => {
  it('renders empty state and disables submit until file + tenant set', () => {
    render(<UploadDropzone onSubmit={vi.fn()} />);
    const submit = screen.getByTestId('upload-submit');
    expect(submit).toBeDisabled();
    expect(screen.queryByTestId('upload-file-row')).toBeNull();
  });

  it('accepts files via change handler and shows them in the list', () => {
    render(<UploadDropzone onSubmit={vi.fn()} defaultTenantId="customer-a" />);
    const input = screen.getByTestId('upload-input') as HTMLInputElement;
    const file = makeFile('rfp.pdf', 1024);
    fireEvent.change(input, { target: { files: [file] } });
    const row = screen.getByTestId('upload-file-row');
    expect(row).toHaveTextContent('rfp.pdf');
    expect(screen.getByTestId('upload-submit')).not.toBeDisabled();
  });

  it('rejects oversize files with an error', () => {
    render(<UploadDropzone onSubmit={vi.fn()} defaultTenantId="customer-a" />);
    const input = screen.getByTestId('upload-input') as HTMLInputElement;
    const oversized = makeFile('huge.pdf', MAX_FILE_BYTES + 1);
    fireEvent.change(input, { target: { files: [oversized] } });
    expect(screen.getByTestId('upload-error')).toHaveTextContent(/files must be/);
    expect(screen.queryByTestId('upload-file-row')).toBeNull();
  });
});
