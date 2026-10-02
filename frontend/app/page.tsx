export default async function Home(){
  const response = await fetch("http://127.0.0.1:8000/experiences");
  const experiences = await response.json();
  return (
    <main>
      <h1>L.I.V.E</h1>
      <h2> Experiences </h2>
      {experiences.map((experience:any)=>(
        <div key= {experience.id}>
          <h3>{experience.title}</h3>

          <p>{experience.description}</p>
          <p>
            Category: {experience.category}
          </p>
          <p>
            Duration: {experience.duration_minutes} minutes
          </p>
        </div>
      )
      )}
    </main>
  );
}