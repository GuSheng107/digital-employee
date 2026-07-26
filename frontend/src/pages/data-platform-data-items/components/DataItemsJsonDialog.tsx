import { Modal } from 'antd';
import styles from '../index.module.css';

export interface DataItemsJsonDialogProps {
  open: boolean;
  jsonText: string;
  onCancel: () => void;
}

export default function DataItemsJsonDialog({ open, jsonText, onCancel }: DataItemsJsonDialogProps) {
  return (
    <Modal
      open={open}
      title="JSON 内容"
      width={640}
      onCancel={onCancel}
      footer={null}
    >
      <pre className={styles.resultBox}>{jsonText}</pre>
    </Modal>
  );
}
