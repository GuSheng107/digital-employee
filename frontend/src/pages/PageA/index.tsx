import styles from './index.module.css';

export default function PageA(): React.ReactElement {
  return (
    <div className={styles.container}>
      <h2 className={styles.title}>页面 A (Page A)</h2>
      <p className={styles.description}>
        PageA
      </p>
    </div>
  );
}
