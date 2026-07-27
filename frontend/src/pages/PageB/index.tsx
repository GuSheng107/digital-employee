import styles from './index.module.css';

export default function PageB(): React.ReactElement {
  return (
    <div className={styles.container}>
      <h2 className={styles.title}>页面 B (Page B)</h2>
      <p className={styles.description}>
        PageB
      </p>
    </div>
  );
}
